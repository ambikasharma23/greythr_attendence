import gradio as gr
import requests
import time
import calendar
from datetime import date
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

GREYTHR_URL = "https://eazydiner.greythr.com"

# ------------------- Selenium Setup -------------------
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    # Hugging Face Spaces Chrome paths (Docker runtime)
    chrome_options.binary_location = "/usr/bin/google-chrome"
    service = Service("/usr/bin/chromedriver")

    return webdriver.Chrome(service=service, options=chrome_options)


# ------------------- Login + Cookie Extraction -------------------
def login_with_selenium(emp_id, password):
    driver = None
    try:
        driver = setup_driver()
        if not driver:
            raise Exception("Could not initialize browser")

        wait = WebDriverWait(driver, 25)
        driver.get(f"{GREYTHR_URL}/uas/portal/auth/login")
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)

        driver.find_element(By.CSS_SELECTOR, "input[name='username']").send_keys(emp_id)
        driver.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(5)

        current_url = driver.current_url.lower()
        if "login" in current_url:
            raise Exception("Login failed - still on login page")

        cookies = driver.get_cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}

        # Validate cookies
        s = requests.Session()
        for n, v in cookie_dict.items():
            s.cookies.set(n, v)
        test = s.post(
            f"{GREYTHR_URL}/v3/login-status",
            headers={"accept": "application/json", "content-type": "application/json"},
            json={},
            timeout=30,
        )
        if test.status_code != 200:
            raise Exception("Login failed (cookie invalid)")

        return cookie_dict
    finally:
        if driver:
            driver.quit()


# ------------------- Helpers -------------------
def get_employee_id(cookies):
    s = requests.Session()
    for n, v in cookies.items():
        s.cookies.set(n, v)
    r = s.post(f"{GREYTHR_URL}/v3/login-status", json={}, timeout=30)
    if r.status_code == 200:
        return r.json().get("user", {}).get("employeeId")
    return None


def get_attendance(cookies, emp_id, date_str):
    s = requests.Session()
    for n, v in cookies.items():
        s.cookies.set(n, v)
    url = f"{GREYTHR_URL}/latte/v3/attendance/info/table/{emp_id}/total?startDate={date_str}&endDate={date_str}"
    r = s.get(url, timeout=30)
    if r.status_code == 200:
        data = r.json().get("data", {})
        total = data.get("totalWorkHrs", 0)
        return parse_work_hours(total)
    return 0


def parse_work_hours(v):
    if not v:
        return 0
    if isinstance(v, str):
        if ":" in v:
            h, m = v.split(":")
            return int(h) * 60 + int(m)
        try:
            return int(float(v) * 60)
        except:
            return 0
    if isinstance(v, (int, float)):
        return int(v * 60) if v < 24 else int(v)
    return 0


def mins_to_hours(m):
    h = m // 60
    mins = m % 60
    return f"{h:02d}:{mins:02d}"


def get_all_dates(year, month):
    today = date.today()
    _, last_day = calendar.monthrange(year, month)
    return [
        date(year, month, d)
        for d in range(1, last_day + 1)
        if date(year, month, d).weekday() != 6 and date(year, month, d) <= today
    ]


def time_to_minutes(t):
    try:
        h, m = map(int, t.split(":"))
        return h * 60 + m
    except:
        return 0


# ------------------- Main Logic (Gradio Function) -------------------
def attendance_action(emp_id, password, year, month):
    try:
        cookies = login_with_selenium(emp_id, password)
        emp_id_server = get_employee_id(cookies)
        if not emp_id_server:
            return "❌ Login failed - Employee ID not found."

        all_dates = get_all_dates(year, month)
        if not all_dates:
            return "No data for this month."

        weekday_times, saturday_times, absent = [], [], []
        REQUIRED_WEEKDAY = 9 * 60
        REQUIRED_SATURDAY = 8 * 60

        for d in all_dates:
            total = get_attendance(cookies, emp_id_server, d.strftime("%Y-%m-%d"))
            if total > 0:
                time_str = mins_to_hours(total)
                (saturday_times if d.weekday() == 5 else weekday_times).append(time_str)
            else:
                absent.append(d.strftime("%Y-%m-%d"))

        weekday_minutes = sum(time_to_minutes(t) for t in weekday_times)
        saturday_minutes = sum(time_to_minutes(t) for t in saturday_times)
        total_worked = weekday_minutes + saturday_minutes
        required_total = len(weekday_times) * REQUIRED_WEEKDAY + len(saturday_times) * REQUIRED_SATURDAY
        diff = total_worked - required_total

        report = f"👤 Employee ID: {emp_id_server}\n📅 Month: {calendar.month_name[month]} {year}\n\n"
        report += f"Weekdays Worked: {len(weekday_times)} ({mins_to_hours(weekday_minutes)})\n"
        report += f"Saturdays Worked: {len(saturday_times)} ({mins_to_hours(saturday_minutes)})\n"
        report += f"Total Worked: {mins_to_hours(total_worked)}\n"
        report += f"Required: {mins_to_hours(required_total)}\n"

        if diff > 0:
            report += f"✅ Surplus: {mins_to_hours(diff)} ({diff} mins)\n"
        elif diff < 0:
            report += f"⚠️ Deficit: {mins_to_hours(-diff)} ({-diff} mins)\n"
        else:
            report += "🎯 Perfect attendance — exact hours met!\n"

        if absent:
            report += f"\n❌ Absent Days:\n" + ", ".join(absent)
        else:
            report += "\n🎉 No absences this month!"

        return report

    except Exception as e:
        return f"⚠️ Error: {str(e)}"


# ------------------- Gradio UI -------------------
years = list(range(2023, date.today().year + 1))
months = list(range(1, 13))

with gr.Blocks(title="GreyHR Attendance Tracker") as app:
    gr.Markdown("## 🚀 GreyHR Attendance Tracker")
    emp_id = gr.Textbox(label="Employee ID", placeholder="ED0683")
    password = gr.Textbox(label="Password", type="password")
    year = gr.Dropdown(choices=years, value=date.today().year, label="Year")
    month = gr.Dropdown(choices=months, value=date.today().month, label="Month")
    output = gr.Textbox(label="Result", lines=20)

    btn = gr.Button("Fetch Attendance")
    btn.click(fn=attendance_action, inputs=[emp_id, password, year, month], outputs=output)

app.launch()
