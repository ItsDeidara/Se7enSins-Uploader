import json
import os
import time
import glob
import traceback
import zipfile
import sqlite3
import pyautogui
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import UnexpectedAlertPresentException
from webdriver_manager.chrome import ChromeDriverManager
import multiprocessing
from multiprocessing import Barrier
from colorama import Fore, Style, init

init()  # Initialize colorama

def print_progress(current, total):
    if total == 0:
        return
    percent = int(100 * current / total)
    bar_length = 20
    filled = bar_length * current // total
    bar = '#' * filled + ' ' * (bar_length - filled)
    print(f"\r{Fore.GREEN}[{bar}]{Style.RESET_ALL} {current}/{total} files processed ({percent}%)", end='', flush=True)
    if current == total:
        print()  # Newline at end

def process_single_zip(zip_path, driver, config, lock, tag_to_use, shared_processed, shared_total, shared_queue, shared_turn, num_browsers, selected_name):
    zip_path = os.path.abspath(zip_path)
    print(f"Processing {zip_path}...")
    
    # Calculate wait time based on file size
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    wait_seconds = int(config.get('upload_wait_base', 30) + size_mb * config.get('upload_wait_per_mb', 0.75))
    print(f"File size: {size_mb:.2f} MB, calculated wait time: {wait_seconds} seconds")
    
    # Get description and tagline from README.md in zip
    description, tagline = get_desc_and_tagline(zip_path)
    print(f"Tagline: {tagline}")
    print(f"Description: {description[:50]}...")  # Preview

    # Fill title (use zip filename without extension)
    title = os.path.basename(zip_path).replace('.zip', '').replace('_', ' ')
    title_input = driver.find_element(By.NAME, "title")
    title_input.clear()
    title_input.send_keys(title)
    print(f"Title filled: {title}")

    # Fill tag line
    tag_line_input = driver.find_element(By.NAME, "tag_line")
    tag_line_input.clear()
    tag_line_input.send_keys(tagline)
    print("Tag line filled.")

    # Fill version string
    version_input = driver.find_element(By.NAME, "version_string")
    version_input.clear()
    version_input.send_keys("1.0.0")
    print("Version set to 1.0.0.")

    # Fill description
    desc_div = driver.find_element(By.CSS_SELECTOR, "div.fr-element")
    desc_div.clear()
    desc_div.send_keys(description)
    print("Description filled.")

    # Fill tags
    tags_text = tag_to_use
    # Remove existing tags
    existing_tags = driver.find_elements(By.CSS_SELECTOR, "tag.tagify__tag")
    for tag in existing_tags:
        try:
            remove_btn = tag.find_element(By.CSS_SELECTOR, ".tagify__tag__removeBtn")
            remove_btn.click()
        except:
            pass
    tags_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "span.tagify__input")))
    tags_input.send_keys(tags_text + Keys.ENTER)
    time.sleep(1)
    # Dismiss dropdown
    tags_input.send_keys(Keys.ESCAPE)
    print(f"Tags set to {tags_text}")

    # Attach files
    attach_button = driver.find_element(By.CSS_SELECTOR, "a.button--icon--attach")
    highlight_element(driver, attach_button)
    driver.execute_script("arguments[0].click();", attach_button)
    print("Attach files clicked.")

    # Wait for file dialog and automate selection
    time.sleep(5)  # Wait for dialog to open
    if lock:
        lock.acquire()
    pyautogui.write(zip_path)  # Write full path to filename field
    pyautogui.press('enter')
    if lock:
        lock.release()
    print("File selected via dialog.")

    # Wait for upload completion
    print("Waiting for file upload to complete...")
    WebDriverWait(driver, config.get('upload_wait_timeout', 180)).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.file-info")))
    for i in range(wait_seconds, 0, -1):
        print(f"Ensuring upload completion: {i} seconds remaining...")
        time.sleep(1)
    print("File uploaded.")

    # Find save button
    save_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[.//span[text()='Save']]")))
    print("Save button found.")

    if config.get('auto_submit', False):
        submission_success = False
        for attempt in range(3):
            try:
                driver.execute_script("arguments[0].click();", save_button)
                print("Form submitted automatically.")
                WebDriverWait(driver, 30).until(lambda d: '/downloads/add' not in d.current_url)
                print("Submission successful, page redirected.")
                time.sleep(2)
                mark_processed(zip_path)
                print(f"Marked {zip_path} as processed.")
                if shared_processed is not None:
                    with shared_processed.get_lock():
                        shared_processed.value += 1
                        print_progress(shared_processed.value, shared_total.value if shared_total else 0)
                submission_success = True
                break
            except UnexpectedAlertPresentException:
                try:
                    alert = driver.switch_to.alert
                    alert.accept()
                    print("Alert accepted, retrying submission.")
                    wait_time = (attempt + 1) * 10
                    print(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                except Exception as e:
                    print(f"Alert handling failed: {e}")
                    break
            except Exception as e:
                print(f"Submission failed: {e}")
                if attempt < 2:
                    wait_time = (attempt + 1) * 10
                    print(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                break
        if not submission_success:
            print("Submission failed after 3 attempts. Skipping this file.")
    else:
        highlight_element(driver, save_button)
        print("Form is ready. Press Enter in terminal to submit.")
        input()
        driver.execute_script("arguments[0].click();", save_button)
        print("Form submitted manually.")
        # Wait for successful submission
        try:
            WebDriverWait(driver, 30).until(lambda d: '/downloads/add' not in d.current_url)
            print("Submission successful, page redirected.")
            time.sleep(2)
            # Mark as processed
            mark_processed(zip_path)
            print(f"Marked {zip_path} as processed.")
            if shared_processed is not None:
                with shared_processed.get_lock():
                    shared_processed.value += 1
                    print_progress(shared_processed.value, shared_total.value if shared_total else 0)
        except Exception as e:
            print(f"Submission failed: {e}")
            print("Not marking as processed.")
    
    if not shared_queue:
        print("Preparing for next upload...")
        driver.get(config['url'])
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.button--cta")))
        
        upload_button = driver.find_element(By.XPATH, "//a[@href='/downloads/add']")
        highlight_element(driver, upload_button)
        upload_button.click()
        
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.overlay")))
        
        # Select same category
        category_link = driver.find_element(By.LINK_TEXT, selected_name)
        highlight_element(driver, category_link)
        category_link.click()
        
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "title")))
        print("Ready for next zip.")
    
    if shared_queue:
        with shared_turn.get_lock():
            shared_turn.value = (shared_turn.value + 1) % num_browsers
from colorama import Fore, Style

def load_config():
    with open('config.json') as f:
        return json.load(f)

def highlight_element(driver, element):
    driver.execute_script("arguments[0].setAttribute('style', 'border: 3px solid red;');", element)
    time.sleep(1)  # Wait for highlight to be visible

def get_desc_and_tagline(zip_path):
    try:
        with zipfile.ZipFile(zip_path) as zf:
            readme_path = None
            for name in zf.namelist():
                if name.lower().endswith('readme.md'):
                    readme_path = name
                    break
            if not readme_path:
                return "No README.md found in the zip file.", "No README"
            content = zf.read(readme_path).decode('utf-8', errors='ignore')
            tagline = content[:100].replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
            # Remove leading "Description:" to save space
            tagline = tagline.lstrip("Description:").lstrip("description:").strip()
            return content, tagline
    except Exception as e:
        return f"Error reading zip: {e}", "Error"

def init_db():
    conn = sqlite3.connect('progress.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS processed_zips (zip_path TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()

def is_processed(zip_path):
    zip_path = os.path.normcase(zip_path)
    conn = sqlite3.connect('progress.db')
    c = conn.cursor()
    c.execute('SELECT 1 FROM processed_zips WHERE zip_path = ?', (zip_path,))
    result = c.fetchone()
    conn.close()
    return result is not None

def mark_processed(zip_path):
    zip_path = os.path.normcase(zip_path)
    conn = sqlite3.connect('progress.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO processed_zips (zip_path) VALUES (?)', (zip_path,))
    conn.commit()
    conn.close()

def run_browser(config, lock=None, zips=None, shared_processed=None, shared_total=None, barrier=None, turn_id=None, shared_turn=None, shared_queue=None, num_browsers=1):
    if zips is None:
        zip_files = glob.glob('zipsToUpload/*.zip')
        zips = [z for z in zip_files if not is_processed(z)]
    print(f"Processing {len(zips)} zips in this browser.")
    
    print("Starting browser...")
    options = Options()
    options.add_argument(f"user-agent={config['user_agent']}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    # options.add_argument("--headless")  # Uncomment for headless mode if needed

    print("Creating Chrome driver...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    print("Driver created successfully.")

    try:
        print("Navigating to se7ensins.com...")
        # Navigate to the domain to add cookies
        driver.get("https://www.se7ensins.com")
        print("Navigated to se7ensins.com.")
        
        # Load cookies from any JSON file in cookies/
        print("Loading cookies...")
        cookie_files = glob.glob('cookies/*.json')
        print(f"Found cookie files: {cookie_files}")
        if not cookie_files:
            print("No cookie JSON file found in cookies/")
            return
        cookie_path = cookie_files[0]  # Use the first valid JSON file
        with open(cookie_path) as f:
            cookies = json.load(f)
        print(f"Loaded {len(cookies)} cookies from {cookie_path}.")
        
        for cookie in cookies:
            # Normalize cookie for Selenium
            if 'sameSite' in cookie:
                if cookie['sameSite'].lower() == 'lax':
                    cookie['sameSite'] = 'Lax'
                elif cookie['sameSite'].lower() == 'strict':
                    cookie['sameSite'] = 'Strict'
                elif cookie['sameSite'].lower() == 'none':
                    cookie['sameSite'] = 'None'
                else:
                    # Remove invalid sameSite
                    del cookie['sameSite']
            driver.add_cookie(cookie)
        print("Cookies added to browser.")
        
        # Navigate to the target URL
        print(f"Navigating to {config['url']}...")
        driver.get(config['url'])
        print("Navigated to target URL.")
        
        # Wait for page to load
        print("Waiting for page to load...")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        print("Page loaded successfully.")
        
        if not config.get('skip_cloudflare', False):
            print("Page loaded. Press Enter after bypassing Cloudflare if needed.")
            input()
        else:
            print("Skipping Cloudflare bypass prompt.")
        
        if barrier:
            print("Waiting for all browsers to be ready...")
            try:
                barrier.wait(timeout=10)
                print("All browsers ready. Starting processing.")
            except Exception as e:
                print(f"Barrier timeout or error: {e}. Proceeding without sync.")
                print("All browsers ready. Starting processing.")
        
        if shared_turn is not None and turn_id is not None:
            print(f"Waiting for my turn ({turn_id})...")
            while shared_turn.value != turn_id:
                time.sleep(1)
            print(f"My turn! Processing zips.")
        
        # Automation sequence
        print("Finding Upload File button...")
        upload_button = driver.find_element(By.XPATH, "//a[@href='/downloads/add']")
        print("Upload button found.")
        highlight_element(driver, upload_button)
        print("Clicking Upload File button...")
        upload_button.click()
        print("Upload button clicked.")
        
        # Wait for category modal
        print("Waiting for category modal...")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.overlay")))
        print("Category modal appeared.")
        
        # Parse categories
        category_links = driver.find_elements(By.CSS_SELECTOR, "a.fauxBlockLink-blockLink")
        categories = []
        for link in category_links:
            name = link.text.strip()
            href = link.get_attribute("href")
            if name and href:
                categories.append((name, href))
        
        # Save to categories.json
        categories_dict = {str(i+1): {'name': name, 'href': href} for i, (name, href) in enumerate(categories)}
        with open('categories.json', 'w') as f:
            json.dump(categories_dict, f, indent=4)
        
        print("Available categories:")
        for i, (name, href) in enumerate(categories, 1):
            print(f"{i}. {name}")
        
        # Check if category_id is set in config
        if config.get('category_id') is not None:
            category_id = str(config['category_id'])
            if category_id in categories_dict:
                selected_name = categories_dict[category_id]['name']
                selected_href = categories_dict[category_id]['href']
                print(f"Auto-selecting category: {selected_name}")
            else:
                print(f"Invalid category_id {category_id} in config. Available: {list(categories_dict.keys())}")
                return
        else:
            # Ask user to select
            while True:
                try:
                    choice = int(input("Enter the number of the category to select: ")) - 1
                    if 0 <= choice < len(categories):
                        selected_name, selected_href = categories[choice]
                        break
                    else:
                        print("Invalid choice. Try again.")
                except ValueError:
                    print("Please enter a number.")
        
        print(f"Selecting category: {selected_name}")
        tag_to_use = config.get('tag')
        if not tag_to_use:
            tag_to_use = input("Enter the tag to use for this session: ")
        # Find the link by link text
        selected_link = driver.find_element(By.LINK_TEXT, selected_name)
        highlight_element(driver, selected_link)
        driver.execute_script("arguments[0].click();", selected_link)
        print("Category selected.")
        
        # Wait for category modal to close
        print("Waiting for category modal to close...")
        WebDriverWait(driver, 10).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.overlay")))
        print("Category modal closed.")
        
        # Wait for upload form
        print("Waiting for upload form...")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "title")))
        print("Upload form loaded.")
        
        if shared_queue is not None:
            while True:
                if shared_turn.value == turn_id:
                    try:
                        zip_path = shared_queue.get_nowait()
                        process_single_zip(zip_path, driver, config, lock, tag_to_use, shared_processed, shared_total, shared_queue, shared_turn, num_browsers, selected_name)
                    except:
                        break
                else:
                    time.sleep(1)
        else:
            for zip_path in zips:
                if not is_processed(zip_path):
                    process_single_zip(zip_path, driver, config, lock, tag_to_use, shared_processed, shared_total, shared_queue, shared_turn, num_browsers, selected_name)
        
    except Exception as e:
        print(f"Error: {e}")
        print("Full traceback:")
        traceback.print_exc()
    finally:
        print("Closing browser...")
        driver.quit()
        print("Browser closed.")

def main():
    config = load_config()
    init_db()
    num_browsers = config.get('num_browsers', 1)
    
    # Pre-install ChromeDriver to avoid conflicts in multiprocessing
    ChromeDriverManager().install()
    
    all_zips = [z for z in glob.glob('zipsToUpload/*.zip') if not is_processed(z)]
    if not all_zips:
        print("No zips to process.")
        return
    shared_total = multiprocessing.Value('i', len(all_zips))
    shared_processed = multiprocessing.Value('i', 0)
    shared_turn = multiprocessing.Value('i', 0)
    
    if num_browsers == 1:
        run_browser(config, None, all_zips, shared_processed, shared_total, None, None, None, None, num_browsers)
    else:
        shared_queue = multiprocessing.Queue()
        for z in all_zips:
            shared_queue.put(z)
        lock = multiprocessing.Lock()
        barrier = multiprocessing.Barrier(num_browsers)
        processes = []
        for i in range(num_browsers):
            p = multiprocessing.Process(target=run_browser, args=(config, lock, None, shared_processed, shared_total, barrier, i, shared_turn, shared_queue, num_browsers))
            p.start()
            processes.append(p)
            if i < num_browsers - 1:
                print("waiting 10 seconds between browser windows to avoid pissing off Cloudflare...")
                time.sleep(10)
        
        for p in processes:
            p.join()

if __name__ == "__main__":
    main()