import streamlit as st
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

def setup_driver():
    """Setup Chrome driver for Streamlit Cloud"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        st.error(f"Failed to setup Chrome driver: {e}")
        return None

def login_with_selenium(emp_id, password):
    """Login using Selenium and return cookies"""
    driver = None
    try:
        driver = setup_driver()
        if not driver:
            raise Exception("Could not initialize browser")
        
        wait = WebDriverWait(driver, 25)
        
        # Navigate to login page
        driver.get(f"{GREYTHR_URL}/uas/portal/auth/login")
        
        # Wait for page to load completely
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        
        # Find and fill form fields
        username_field = driver.find_element(By.CSS_SELECTOR, "input[name='username']")
        username_field.clear()
        username_field.send_keys(emp_id)
        
        password_field = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
        password_field.clear()
        password_field.send_keys(password)
        
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].click();", login_button)
        
        # Wait for login to complete
        st.write("⏳ Waiting for login to complete...")
        time.sleep(5)
        
        # Check if login was successful
        current_url = driver.current_url.lower()
        if any(keyword in current_url for keyword in ["dashboard", "home", "latte", "v3/portal"]):
            pass  # Login successful
        else:
            # Wait more and check again
            time.sleep(3)
            current_url = driver.current_url.lower()
            if "login" in current_url or "auth" in current_url:
                raise Exception("Login failed - still on login page")
        
        # Get ALL cookies including session cookies
        cookies = driver.get_cookies()
        cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
        
        # Verify cookies work by making a test request
        test_session = requests.Session()
        for name, value in cookie_dict.items():
            test_session.cookies.set(name, value)
        
        test_response = test_session.post(
            f"{GREYTHR_URL}/v3/login-status",
            headers={
                "accept": "application/json",
                "content-type": "application/json", 
                "x-requested-with": "XMLHttpRequest",
                "referer": f"{GREYTHR_URL}/v3/portal",
            },
            json={},
            timeout=30
        )
        
        if test_response.status_code != 200:
            raise Exception("Cookies verification failed")
        
        return cookie_dict
        
    except Exception as e:
        raise e
        
    finally:
        if driver:
            driver.quit()

def get_employee_id(cookies):
    """Get employee ID using cookies"""
    session = requests.Session()
    
    # Set all cookies
    for name, value in cookies.items():
        session.cookies.set(name, value)
    
    headers = {
        "accept": "application/json",
        "content-type": "application/json", 
        "x-requested-with": "XMLHttpRequest",
        "referer": f"{GREYTHR_URL}/v3/portal",
    }
    
    try:
        response = session.post(f"{GREYTHR_URL}/v3/login-status", headers=headers, json={}, timeout=30)
        if response.status_code == 200:
            data = response.json()
            emp_id = data.get("user", {}).get("employeeId")
            if emp_id:
                return emp_id
    except:
        pass
    
    return None

def get_attendance(cookies, emp_id, date_str):
    """Get attendance data for specific date"""
    session = requests.Session()
    
    # Set all cookies
    for name, value in cookies.items():
        session.cookies.set(name, value)
    
    headers = {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'{GREYTHR_URL}/v3/portal',
    }
    
    try:
        url = f"{GREYTHR_URL}/latte/v3/attendance/info/table/{emp_id}/total?startDate={date_str}&endDate={date_str}"
        res = session.get(url, headers=headers, timeout=30)
        
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict):
                data = data.get("data", data)
                total_hrs = data.get("totalWorkHrs", 0)
                return parse_work_hours(total_hrs)
    except:
        pass
    
    return 0

def check_session_valid(cookies):
    """Check if the session is still valid"""
    session = requests.Session()
    for name, value in cookies.items():
        session.cookies.set(name, value)
    
    headers = {
        "accept": "application/json",
        "content-type": "application/json", 
        "x-requested-with": "XMLHttpRequest",
        "referer": f"{GREYTHR_URL}/v3/portal",
    }
    
    try:
        response = session.post(f"{GREYTHR_URL}/v3/login-status", headers=headers, json={}, timeout=30)
        return response.status_code == 200
    except:
        return False

def parse_work_hours(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value * 60) if value < 24 else int(value)
    if isinstance(value, str):
        value = value.strip()
        if ":" in value:
            h, m = value.split(":")
            return int(h) * 60 + int(m)
        try:
            hours = float(value)
            return int(hours * 60)
        except ValueError:
            return 0
    return 0

def mins_to_hours(m):
    h = m // 60
    mins = m % 60
    return f"{h:02d}:{mins:02d}"

def time_to_minutes(time_str):
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes
    except:
        return 0

def get_all_dates(year, month):
    today = date.today()
    _, last_day = calendar.monthrange(year, month)
    return [
        date(year, month, d)
        for d in range(1, last_day + 1)
        if date(year, month, d).weekday() != 6 and date(year, month, d) <= today
    ]

def main():
    st.set_page_config(page_title="GreyHR Attendance", page_icon="📅", layout="centered")
    st.title("🚀 GreyHR Attendance Tracker")
    
    # Initialize session state
    if 'cookies' not in st.session_state:
        st.session_state.cookies = None
    if 'employee_id' not in st.session_state:
        st.session_state.employee_id = None
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    # Login section
    st.write("### 🔑 Login")
    
    with st.form("login_form"):
        emp_id = st.text_input("Employee ID", value="ED0683", placeholder="ED0683")
        password = st.text_input("Password", type="password")
        login_submitted = st.form_submit_button("Login")
    
    if login_submitted:
        if not emp_id or not password:
            st.error("Please enter credentials")
            return
            
        with st.spinner("Logging in..."):
            try:
                cookies = login_with_selenium(emp_id, password)
                employee_id = get_employee_id(cookies)
                
                if employee_id:
                    # Store in session state
                    st.session_state.cookies = cookies
                    st.session_state.employee_id = employee_id
                    st.session_state.logged_in = True
                    st.success(f"✅ Login successful! Employee ID: {employee_id}")
                else:
                    st.error("❌ Login failed - could not get employee ID")
                    
            except Exception as e:
                st.error(f"❌ Login failed: {str(e)}")
    
    # Check if user is logged in
    if not st.session_state.logged_in or not st.session_state.cookies:
        st.warning("Please login first")
        return
    
    # Verify session is still valid
    if not check_session_valid(st.session_state.cookies):
        st.error("Session expired. Please login again.")
        st.session_state.logged_in = False
        st.session_state.cookies = None
        st.session_state.employee_id = None
        return
    
    # Attendance section - only show if logged in
    st.write("### 📊 Attendance Data")
    st.success(f"Logged in as Employee ID: {st.session_state.employee_id}")
    
    col1, col2 = st.columns(2)
    with col1:
        year = st.selectbox("Select Year", list(range(2023, date.today().year + 1)), 
                          index=len(range(2023, date.today().year + 1)) - 1)
    with col2:
        month = st.selectbox("Select Month", list(range(1, 13)), index=date.today().month - 1)
    
    if st.button("Get Attendance Data"):
        with st.spinner(f"Fetching attendance for {calendar.month_name[month]} {year}..."):
            # Double-check session before proceeding
            if not check_session_valid(st.session_state.cookies):
                st.error("Session expired during request. Please login again.")
                st.session_state.logged_in = False
                st.session_state.cookies = None
                st.session_state.employee_id = None
                return
            
            all_dates = get_all_dates(year, month)
            
            if not all_dates:
                st.warning("No dates to process for the selected month.")
                return
                
            weekday_times, saturday_times, absent_days = [], [], []
            REQUIRED_WEEKDAY = 9 * 60
            REQUIRED_SATURDAY = 8 * 60
            
            progress_bar = st.progress(0)
            
            for i, d in enumerate(all_dates):
                date_str = d.strftime("%Y-%m-%d")
                
                # Check session periodically
                if i % 5 == 0 and not check_session_valid(st.session_state.cookies):
                    st.error("Session expired during data fetch. Please login again.")
                    st.session_state.logged_in = False
                    st.session_state.cookies = None
                    st.session_state.employee_id = None
                    return
                
                total_work = get_attendance(st.session_state.cookies, st.session_state.employee_id, date_str)
                is_saturday = d.weekday() == 5
                
                if total_work > 0:
                    hrs = total_work // 60
                    mins = total_work % 60
                    time_str = f"{hrs:02d}:{mins:02d}"
                    (saturday_times if is_saturday else weekday_times).append(time_str)
                else:
                    absent_days.append(date_str)
                
                progress_bar.progress((i + 1) / len(all_dates))
                time.sleep(0.2)
            
            # Calculate results
            weekday_minutes = sum(time_to_minutes(t) for t in weekday_times)
            saturday_minutes = sum(time_to_minutes(t) for t in saturday_times)
            total_worked = weekday_minutes + saturday_minutes
            required_total = len(weekday_times) * REQUIRED_WEEKDAY + len(saturday_times) * REQUIRED_SATURDAY
            difference = total_worked - required_total
            
            # Display results
            st.subheader("📊 Attendance Summary")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Weekdays Worked", len(weekday_times), mins_to_hours(weekday_minutes))
                st.metric("Saturdays Worked", len(saturday_times), mins_to_hours(saturday_minutes))
            with col2:
                st.metric("Total Worked", mins_to_hours(total_worked))
                st.metric("Required Total", mins_to_hours(required_total))
            
            if difference > 0:
                st.success(f"✅ Surplus: {mins_to_hours(difference)} ({difference} minutes)")
            elif difference < 0:
                st.warning(f"⚠️ Deficit: {mins_to_hours(-difference)} ({-difference} minutes)")
            else:
                st.info("🎯 Perfect attendance — exact hours met!")
            
            if absent_days:
                st.write("### 📆 Absent Days")
                st.write(", ".join(absent_days))
            else:
                st.success("🎉 No absences this month!")
    
    # Logout button
    st.write("---")
    if st.button("Logout"):
        st.session_state.cookies = None
        st.session_state.employee_id = None
        st.session_state.logged_in = False
        st.success("Logged out successfully!")
        st.experimental_rerun()

if __name__ == "__main__":
    main()
