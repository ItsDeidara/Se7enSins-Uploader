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
from multiprocessing import Barrier, Queue
from colorama import Fore, Style, init
import tkinter as tk
import TKinterModernThemes as TKMT
import threading
import logging
import queue

import re

init()  # Initialize colorama

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        if record.levelno >= logging.ERROR:
            return Fore.RED + msg + Style.RESET_ALL
        elif record.levelno >= logging.WARNING:
            return Fore.YELLOW + msg + Style.RESET_ALL
        elif record.levelno >= logging.INFO:
            return Fore.BLUE + msg + Style.RESET_ALL
        else:
            return msg

# Logging setup
log_queue = Queue()
progress_queue = Queue()

class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = QueueHandler(log_queue)
formatter = ColoredFormatter('%(asctime)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def print_progress(current, total):
    if total == 0:
        return
    percent = int(100 * current / total)
    bar_length = 20
    filled = bar_length * current // total
    bar = '#' * filled + ' ' * (bar_length - filled)
    message = f"[{bar}] {current}/{total} files processed ({percent}%)"
    logger.info(message)
    progress_queue.put((current, total))
    if current == total:
        logger.info("Upload complete!")

def process_single_zip(zip_path, driver, config, lock, tag_to_use, shared_processed, shared_total, shared_queue, shared_turn, num_browsers, selected_name):
    zip_path = os.path.abspath(zip_path)
    logger.info(f"Processing {zip_path}...")
    
    # Calculate wait time based on file size
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    wait_seconds = int(config.get('upload_wait_base', 30) + size_mb * config.get('upload_wait_per_mb', 0.75))
    logger.info(f"File size: {size_mb:.2f} MB, calculated wait time: {wait_seconds} seconds")
    
    # Get description and tagline from README.md in zip
    description, tagline = get_desc_and_tagline(zip_path)
    logger.info(f"Tagline: {tagline}")
    logger.info(f"Description: {description[:50]}...")  # Preview

    # Fill title (use zip filename without extension)
    logger.info("Step: Filling title...")
    title = os.path.basename(zip_path).replace('.zip', '').replace('_', ' ')
    title_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='title']")))
    highlight_element(driver, title_input)
    driver.execute_script("arguments[0].value = arguments[1];", title_input, title)
    logger.info(f"Title filled: {title}")
    if config.get('manual_mode', False):
        input("Press Enter to continue after filling title...")

    # Fill tag line
    logger.info("Step: Filling tag line...")
    tag_line_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='tag_line']")))
    highlight_element(driver, tag_line_input)
    driver.execute_script("arguments[0].value = arguments[1];", tag_line_input, tagline)
    logger.info("Tag line filled.")
    if config.get('manual_mode', False):
        input("Press Enter to continue after filling tag line...")

    # Fill version string
    logger.info("Step: Filling version string...")
    version_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='version_string']")))
    highlight_element(driver, version_input)
    driver.execute_script("arguments[0].value = arguments[1];", version_input, "1.0.0")
    logger.info("Version set to 1.0.0.")
    if config.get('manual_mode', False):
        input("Press Enter to continue after filling version...")

    # Fill description
    logger.info("Step: Filling description...")
    desc_div = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.fr-element")))
    highlight_element(driver, desc_div)
    driver.execute_script("arguments[0].innerHTML = arguments[1];", desc_div, description)
    logger.info("Description filled.")
    if config.get('manual_mode', False):
        input("Press Enter to continue after filling description...")

    # Fill tags
    logger.info("Step: Filling tags...")
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
    highlight_element(driver, tags_input)
    tags_input.send_keys(tags_text + Keys.ENTER)
    time.sleep(1)
    # Dismiss dropdown
    tags_input.send_keys(Keys.ESCAPE)
    logger.info(f"Tags set to {tags_text}")
    if config.get('manual_mode', False):
        input("Press Enter to continue after filling tags...")

    # Attach files
    logger.info("Step: Attaching files...")
    attach_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.button--icon--attach")))
    highlight_element(driver, attach_button)
    main_window = driver.current_window_handle
    driver.execute_script("arguments[0].click();", attach_button)
    logger.info("Attach files clicked.")

    # Wait for file dialog and automate selection
    time.sleep(5)  # Wait for dialog to open
    pyautogui.write(zip_path)  # Write full path to filename field
    pyautogui.press('enter')
    logger.info("File selected via dialog.")

    # Wait for upload completion
    logger.info("Step: Waiting for file upload to complete...")
    WebDriverWait(driver, config.get('upload_wait_timeout', 180)).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.file-info")))
    for i in range(wait_seconds, 0, -1):
        logger.info(f"Ensuring upload completion: {i} seconds remaining...")
        time.sleep(1)
    logger.info("File uploaded.")
    if config.get('manual_mode', False):
        input("Press Enter to continue after upload completion...")

    # Find save button
    logger.info("Step: Finding save button...")
    save_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[.//span[text()='Save']]")))
    highlight_element(driver, save_button)
    logger.info("Save button found.")
    if config.get('manual_mode', False):
        input("Press Enter to continue after finding save button...")

    if config.get('auto_submit', False):
        logger.info("Step: Auto-submitting form...")
        submission_success = False
        for attempt in range(3):
            try:
                driver.execute_script("arguments[0].click();", save_button)
                logger.info("Form submitted automatically.")
                WebDriverWait(driver, 30).until(lambda d: '/downloads/add' not in d.current_url)
                logger.info("Submission successful, page redirected.")
                time.sleep(2)
                zip_path = os.path.relpath(zip_path)
                mark_processed(zip_path)
                logger.info(f"Marked {zip_path} as processed.")
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
                    logger.info("Alert accepted, retrying submission.")
                    wait_time = (attempt + 1) * 10
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                except Exception as e:
                    logger.info(f"Alert handling failed: {e}")
                    break
            except Exception as e:
                logger.info(f"Submission failed: {e}")
                if attempt < 2:
                    wait_time = (attempt + 1) * 10
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                break
        if not submission_success:
            logger.info("Submission failed after 3 attempts. Skipping this file.")
    else:
        highlight_element(driver, save_button)
        logger.info("Form is ready. Press Enter in terminal to submit.")
        input()
        driver.execute_script("arguments[0].click();", save_button)
        logger.info("Form submitted manually.")
        # Wait for successful submission
        try:
            WebDriverWait(driver, 30).until(lambda d: '/downloads/add' not in d.current_url)
            logger.info("Submission successful, page redirected.")
            time.sleep(2)
            # Mark as processed
            zip_path = os.path.relpath(zip_path)
            mark_processed(zip_path)
            logger.info(f"Marked {zip_path} as processed.")
            if shared_processed is not None:
                with shared_processed.get_lock():
                    shared_processed.value += 1
                    print_progress(shared_processed.value, shared_total.value if shared_total else 0)
        except Exception as e:
            logger.info(f"Submission failed: {e}")
            print(f"{Fore.YELLOW}Not marking as processed.{Style.RESET_ALL}")
    
    if not shared_queue:
        logger.info("Preparing for next upload...")
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
        logger.info("Ready for next zip.")
    
    if shared_queue:
        with shared_turn.get_lock():
            shared_turn.value = (shared_turn.value + 1) % num_browsers
from colorama import Fore, Style

def get_categories(config):
    logger.info("Fetching categories...")
    options = Options()
    options.add_argument(f"user-agent={config['user_agent']}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--headless")  # Headless for category loading

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    try:
        driver.get("https://www.se7ensins.com")
        cookie_files = glob.glob('cookies/*.json')
        if cookie_files:
            cookie_path = cookie_files[0]
            with open(cookie_path) as f:
                cookies = json.load(f)
            for cookie in cookies:
                if 'sameSite' in cookie:
                    if cookie['sameSite'].lower() == 'lax':
                        cookie['sameSite'] = 'Lax'
                    elif cookie['sameSite'].lower() == 'strict':
                        cookie['sameSite'] = 'Strict'
                    elif cookie['sameSite'].lower() == 'none':
                        cookie['sameSite'] = 'None'
                    else:
                        del cookie['sameSite']
                driver.add_cookie(cookie)
        
        driver.get(config['url'])
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        
        upload_button = driver.find_element(By.XPATH, "//a[@href='/downloads/add']")
        upload_button.click()
        
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.overlay")))
        
        category_links = driver.find_elements(By.CSS_SELECTOR, "a.fauxBlockLink-blockLink")
        categories = []
        for link in category_links:
            name = link.text.strip()
            href = link.get_attribute("href")
            if name and href:
                categories.append((name, href))
        
        categories_dict = {str(i+1): {'name': name, 'href': href} for i, (name, href) in enumerate(categories)}
        with open('categories.json', 'w') as f:
            json.dump(categories_dict, f, indent=4)
        
        logger.info(f"Loaded {len(categories)} categories.")
        return categories
    except Exception as e:
        logger.info(f"Error loading categories: {e}")
        return []
    finally:
        driver.quit()

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
            base_name = os.path.basename(zip_path).replace('.zip', '').replace('_', ' ')
            if not readme_path:
                # Use filename (without .zip) when README is missing
                return base_name, base_name
            content = zf.read(readme_path).decode('utf-8', errors='ignore')
            if not content or not content.strip():
                # Use filename when README is empty
                return base_name, base_name
            tagline = content[:100].replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
            # Remove leading "Description:" to save space
            tagline = tagline.lstrip("Description:").lstrip("description:").strip()
            if not tagline:
                tagline = base_name
            description = content[:200]  # Limit description to 200 characters
            return description, tagline
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
    logger.info(f"Processing {len(zips)} zips in this browser.")
    
    logger.info("Starting browser...")
    options = Options()
    options.add_argument(f"user-agent={config['user_agent']}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    # options.add_argument("--headless")  # Uncomment for headless mode if needed

    logger.info("Creating Chrome driver...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    logger.info("Driver created successfully.")

    try:
        logger.info("Navigating to se7ensins.com...")
        # Navigate to the domain to add cookies
        driver.get("https://www.se7ensins.com")
        logger.info("Navigated to se7ensins.com.")
        
        # Load cookies from any JSON file in cookies/
        logger.info("Loading cookies...")
        cookie_files = glob.glob('cookies/*.json')
        logger.info(f"Found cookie files: {cookie_files}")
        if not cookie_files:
            logger.info("No cookie JSON file found in cookies/")
            return
        cookie_path = cookie_files[0]  # Use the first valid JSON file
        with open(cookie_path) as f:
            cookies = json.load(f)
        logger.info(f"Loaded {len(cookies)} cookies from {cookie_path}.")
        
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
        logger.info("Cookies added to browser.")
        
        # Navigate to the target URL
        logger.info(f"Navigating to {config['url']}...")
        driver.get(config['url'])
        logger.info("Navigated to target URL.")
        
        # Wait for page to load
        logger.info("Waiting for page to load...")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        logger.info("Page loaded successfully.")
        
        if not config.get('skip_cloudflare', False):
            logger.info("Page loaded. Press Enter after bypassing Cloudflare if needed.")
            input()
        else:
            logger.info("Skipping Cloudflare bypass prompt.")
        
        if barrier:
            logger.info("Waiting for all browsers to be ready...")
            try:
                barrier.wait(timeout=10)
                logger.info("All browsers ready. Starting processing.")
            except Exception as e:
                logger.info(f"Barrier timeout or error: {e}. Proceeding without sync.")
                logger.info("All browsers ready. Starting processing.")
        
        if shared_turn is not None and turn_id is not None:
            logger.info(f"Waiting for my turn ({turn_id})...")
            while shared_turn.value != turn_id:
                time.sleep(1)
            logger.info("My turn! Processing zips.")
        
        # Automation sequence
        logger.info("Finding Upload File button...")
        upload_button = driver.find_element(By.XPATH, "//a[@href='/downloads/add']")
        logger.info("Upload button found.")
        highlight_element(driver, upload_button)
        logger.info("Clicking Upload File button...")
        upload_button.click()
        logger.info("Upload button clicked.")
        
        # Wait for category modal
        logger.info("Waiting for category modal...")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.overlay")))
        logger.info("Category modal appeared.")
        
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
        
        logger.info("Available categories:")
        for i, (name, href) in enumerate(categories, 1):
            logger.info(f"{i}. {name}")
        
        # Check if category_id is set in config
        if config.get('category_id') is not None:
            category_id = str(config['category_id'])
            if category_id in categories_dict:
                selected_name = categories_dict[category_id]['name']
                selected_href = categories_dict[category_id]['href']
                logger.info(f"Auto-selecting category: {selected_name}")
            else:
                logger.info(f"Invalid category_id {category_id} in config. Available: {list(categories_dict.keys())}")
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
                        print(f"{Fore.YELLOW}Invalid choice. Try again.{Style.RESET_ALL}")
                except ValueError:
                    print(f"{Fore.YELLOW}Please enter a number.{Style.RESET_ALL}")
        
        logger.info(f"Selecting category: {selected_name}")
        tag_to_use = config.get('tag')
        if not tag_to_use:
            tag_to_use = "default tag"  # or something, but since config has it, fine
        # Find the link by link text
        selected_link = driver.find_element(By.LINK_TEXT, selected_name)
        highlight_element(driver, selected_link)
        driver.execute_script("arguments[0].click();", selected_link)
        logger.info("Category selected.")
        
        # Wait for category modal to close
        logger.info("Waiting for category modal to close...")
        WebDriverWait(driver, 10).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.overlay")))
        logger.info("Category modal closed.")
        
        # Wait for upload form
        logger.info("Waiting for upload form...")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "title")))
        logger.info("Upload form loaded.")
        
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
            for i, zip_path in enumerate(zips, 1):
                logger.info(f"Processing {i}/{len(zips)} : {os.path.basename(zip_path)}")
                process_single_zip(zip_path, driver, config, lock, tag_to_use, shared_processed, shared_total, shared_queue, shared_turn, num_browsers, selected_name)
        
    except Exception as e:
        logger.info(f"Error: {e}")
        logger.info("Full traceback:")
        traceback.print_exc()
    finally:
        logger.info("Closing browser...")
        driver.quit()
        logger.info("Browser closed.")

def main():
    config = load_config()
    init_db()
    num_browsers = config.get('num_browsers', 1)
    
    # Pre-install ChromeDriver to avoid conflicts in multiprocessing
    ChromeDriverManager().install()
    
    all_zips = [z for z in glob.glob('zipsToUpload/*.zip') if not is_processed(z)]
    if not all_zips:
        logger.info("No zips to process.")
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
                logger.info("waiting 10 seconds between browser windows to avoid pissing off Cloudflare...")
                time.sleep(10)
        
        for p in processes:
            p.join()

if __name__ == "__main__":
    config = load_config()
    config['manual_mode'] = False  # Disable for GUI
    
    import tkinter.ttk as ttk
    
    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title("Se7enSins Uploader")
            self.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.config_data = config.copy()
            self.categories = []
            self.zip_files = glob.glob('zipsToUpload/*.zip')
            self.total_zips = len(self.zip_files)
            
            self.build_ui()
            if os.path.exists('categories.json'):
                self._load_categories_from_file()
            self.update_progress_from_db()
            self.poll_logs()
            self.poll_progress()
            self.poll_db_progress()
        
        def build_ui(self):
            
            
            # Config Section
            config_frame = tk.LabelFrame(self, text="Config Editing")
            config_frame.pack(pady=5, padx=5, fill="x")
            
            tk.Label(config_frame, text="URL:").grid(row=0, column=0, sticky="w")
            self.url_entry = tk.Entry(config_frame)
            self.url_entry.insert(0, self.config_data.get('url', ''))
            self.url_entry.grid(row=0, column=1, padx=5, pady=2)
            
            tk.Label(config_frame, text="User Agent:").grid(row=1, column=0, sticky="w")
            self.ua_entry = tk.Entry(config_frame)
            self.ua_entry.insert(0, self.config_data.get('user_agent', ''))
            self.ua_entry.grid(row=1, column=1, padx=5, pady=2)
            
            tk.Label(config_frame, text="Upload Wait Base:").grid(row=2, column=0, sticky="w")
            self.wait_base_entry = tk.Entry(config_frame)
            self.wait_base_entry.insert(0, str(self.config_data.get('upload_wait_base', 30)))
            self.wait_base_entry.grid(row=2, column=1, padx=5, pady=2)
            
            tk.Label(config_frame, text="Upload Wait Per MB:").grid(row=3, column=0, sticky="w")
            self.wait_per_mb_entry = tk.Entry(config_frame)
            self.wait_per_mb_entry.insert(0, str(self.config_data.get('upload_wait_per_mb', 0.75)))
            self.wait_per_mb_entry.grid(row=3, column=1, padx=5, pady=2)
            
            self.manual_mode_var = tk.BooleanVar(value=self.config_data.get('manual_mode', False))
            tk.Checkbutton(config_frame, text="Manual Mode", variable=self.manual_mode_var).grid(row=4, column=0, columnspan=2, sticky="w")
            
            self.auto_submit_var = tk.BooleanVar(value=self.config_data.get('auto_submit', True))
            tk.Checkbutton(config_frame, text="Auto Submit", variable=self.auto_submit_var).grid(row=5, column=0, columnspan=2, sticky="w")
            
            tk.Label(config_frame, text="Upload Wait Timeout:").grid(row=6, column=0, sticky="w")
            self.timeout_entry = tk.Entry(config_frame)
            self.timeout_entry.insert(0, str(self.config_data.get('upload_wait_timeout', 180)))
            self.timeout_entry.grid(row=6, column=1, padx=5, pady=2)
            
            self.skip_cf_var = tk.BooleanVar(value=self.config_data.get('skip_cloudflare', True))
            tk.Checkbutton(config_frame, text="Skip Cloudflare", variable=self.skip_cf_var).grid(row=7, column=0, columnspan=2, sticky="w")
            
            tk.Label(config_frame, text="Category ID:").grid(row=8, column=0, sticky="w")
            self.cat_id_entry = tk.Entry(config_frame)
            self.cat_id_entry.insert(0, str(self.config_data.get('category_id', '')))
            self.cat_id_entry.grid(row=8, column=1, padx=5, pady=2)
            self.cat_id_entry.bind('<KeyRelease>', self.on_id_change)
            
            tk.Button(config_frame, text="Load Categories", command=self.load_categories).grid(row=9, column=0, sticky="w")
            self.cat_combo = ttk.Combobox(config_frame, state="readonly")
            self.cat_combo.grid(row=9, column=1, padx=5, pady=2)
            self.cat_combo.bind("<<ComboboxSelected>>", self.on_cat_select)
            
            tk.Label(config_frame, text="Tag:").grid(row=10, column=0, sticky="w")
            self.tag_entry = tk.Entry(config_frame)
            self.tag_entry.insert(0, str(self.config_data.get('tag', '')))
            self.tag_entry.grid(row=10, column=1, padx=5, pady=2)
            
            tk.Label(config_frame, text="Num Browsers:").grid(row=11, column=0, sticky="w")
            self.num_browsers_entry = tk.Entry(config_frame)
            self.num_browsers_entry.insert(0, str(self.config_data.get('num_browsers', 1)))
            self.num_browsers_entry.grid(row=11, column=1, padx=5, pady=2)
            
            tk.Button(config_frame, text="Save Config", command=self.save_config).grid(row=12, column=0, columnspan=2, pady=5)
            
            # Upload Section
            upload_frame = tk.LabelFrame(self, text="Upload Control")
            upload_frame.pack(pady=5, padx=5, fill="x")
            tk.Button(upload_frame, text="Start Upload", command=self.start_upload).grid(row=0, column=0, pady=5)
            tk.Button(upload_frame, text="Stop Upload", command=self.stop_upload).grid(row=0, column=1, pady=5)
            
            # Progress
            progress_frame = tk.LabelFrame(self, text="Progress")
            progress_frame.pack(pady=5, padx=5, fill="x")
            self.progress_bar = ttk.Progressbar(progress_frame, length=400, mode='determinate')
            self.progress_bar.pack(pady=5)
            self.progress_label = tk.Label(progress_frame, text="0/0")
            self.progress_label.pack(pady=5)
            
            # Logs
            logs_frame = tk.LabelFrame(self, text="Logs")
            logs_frame.pack(pady=5, padx=5, fill="both", expand=True)
            self.logs_text = tk.Text(logs_frame, height=15, width=80)
            self.logs_text.pack(pady=5, padx=5, fill="both", expand=True)
            
        def save_config(self):
            self.config_data['url'] = self.url_entry.get()
            self.config_data['user_agent'] = self.ua_entry.get()
            self.config_data['upload_wait_base'] = int(self.wait_base_entry.get())
            self.config_data['upload_wait_per_mb'] = float(self.wait_per_mb_entry.get())
            self.config_data['manual_mode'] = self.manual_mode_var.get()
            self.config_data['auto_submit'] = self.auto_submit_var.get()
            self.config_data['upload_wait_timeout'] = int(self.timeout_entry.get())
            self.config_data['skip_cloudflare'] = self.skip_cf_var.get()
            self.config_data['category_id'] = int(self.cat_id_entry.get()) if self.cat_id_entry.get() else None
            self.config_data['tag'] = self.tag_entry.get()
            self.config_data['num_browsers'] = int(self.num_browsers_entry.get())
            with open('config.json', 'w') as f:
                json.dump(self.config_data, f, indent=4)
            logger.info("Config saved.")
        
        def load_categories(self):
            threading.Thread(target=self._load_categories).start()
        
        def _load_categories(self):
            cats = get_categories(self.config_data)
            self.categories = [name for name, href in cats]
            self.cat_combo['values'] = [f"{i+1}. {name}" for i, name in enumerate(self.categories)]
            if self.config_data.get('category_id'):
                id_val = self.config_data['category_id']
                if 1 <= id_val <= len(self.categories):
                    self.cat_combo.set(f"{id_val}. {self.categories[id_val-1]}")
        
        def _load_categories_from_file(self):
            with open('categories.json') as f:
                data = json.load(f)
            self.categories = [(data[str(i+1)]['name'], data[str(i+1)]['href']) for i in range(len(data))]
            self.cat_combo['values'] = [f"{i+1}. {name}" for i, (name, href) in enumerate(self.categories)]
            if self.config_data.get('category_id'):
                id_val = self.config_data['category_id']
                if 1 <= id_val <= len(self.categories):
                    self.cat_combo.set(f"{id_val}. {self.categories[id_val-1][0]}")
        
        def on_cat_select(self, event):
            selected = self.cat_combo.get()
            if selected:
                num = selected.split('.')[0]
                self.cat_id_entry.delete(0, tk.END)
                self.cat_id_entry.insert(0, num)
        
        def on_id_change(self, event):
            try:
                id_val = int(self.cat_id_entry.get())
                if 1 <= id_val <= len(self.categories):
                    self.cat_combo.set(f"{id_val}. {self.categories[id_val-1]}")
                else:
                    self.cat_combo.set('')
            except ValueError:
                self.cat_combo.set('')
        
        def start_upload(self):
            threading.Thread(target=main).start()
        
        def stop_upload(self):
            os.system('taskkill /f /im chrome.exe >nul 2>&1')
            logger.info("Upload stopped, Chrome processes killed.")
        
        def poll_logs(self):
            while not log_queue.empty():
                msg = log_queue.get()
                self.insert_colored_text(msg)
            self.after(100, self.poll_logs)
        
        def insert_colored_text(self, text):
            self.logs_text.tag_configure('red', foreground='red')
            self.logs_text.tag_configure('green', foreground='green')
            self.logs_text.tag_configure('blue', foreground='blue')
            self.logs_text.tag_configure('yellow', foreground='yellow')
            
            ansi_pattern = re.compile(r'(\x1b\[[0-9;]*m)')
            parts = ansi_pattern.split(text)
            current_tag = None
            for part in parts:
                if ansi_pattern.match(part):
                    code = part
                    if code == '\x1b[31m':
                        current_tag = 'red'
                    elif code == '\x1b[32m':
                        current_tag = 'green'
                    elif code == '\x1b[34m':
                        current_tag = 'blue'
                    elif code == '\x1b[33m':
                        current_tag = 'yellow'
                    elif code == '\x1b[0m':
                        current_tag = None
                else:
                    self.logs_text.insert(tk.END, part, current_tag)
            self.logs_text.insert(tk.END, '\n')
            self.logs_text.see(tk.END)
        
        def poll_progress(self):
            while not progress_queue.empty():
                current, total = progress_queue.get()
                self.progress_bar['maximum'] = total
                self.progress_bar['value'] = current
                self.progress_label.config(text=f"{current}/{total}")
            self.update_idletasks()
            self.after(100, self.poll_progress)
        
        def update_progress_from_db(self):
            if os.path.exists('progress.db'):
                conn = sqlite3.connect('progress.db')
                c = conn.cursor()
                try:
                    c.execute('SELECT COUNT(*) FROM processed')
                    processed = c.fetchone()[0]
                except sqlite3.OperationalError:
                    processed = 0
                conn.close()
                self.progress_bar['maximum'] = self.total_zips
                self.progress_bar['value'] = processed
                self.progress_label.config(text=f"{processed}/{self.total_zips}")
            else:
                self.progress_label.config(text=f"0/{self.total_zips}")
            self.update_idletasks()
        
        def poll_db_progress(self):
            self.update_progress_from_db()
            self.after(30000, self.poll_db_progress)
        
        def on_closing(self):
            os.system('taskkill /f /im chrome.exe >nul 2>&1')
            self.destroy()
    
    app = App()
    app.mainloop()