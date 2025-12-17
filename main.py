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
    print(f"{Fore.CYAN}Processing {zip_path}...{Style.RESET_ALL}")
    
    # Calculate wait time based on file size
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    wait_seconds = int(config.get('upload_wait_base', 30) + size_mb * config.get('upload_wait_per_mb', 0.75))
    print(f"{Fore.CYAN}File size: {size_mb:.2f} MB, calculated wait time: {wait_seconds} seconds{Style.RESET_ALL}")
    
    # Get description and tagline from README.md in zip
    description, tagline = get_desc_and_tagline(zip_path)
    print(f"{Fore.CYAN}Tagline: {tagline}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Description: {description[:50]}...{Style.RESET_ALL}")  # Preview

    # Fill title (use zip filename without extension)
    print(f"{Fore.YELLOW}Step: Filling title...{Style.RESET_ALL}")
    title = os.path.basename(zip_path).replace('.zip', '').replace('_', ' ')
    title_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='title']")))
    highlight_element(driver, title_input)
    driver.execute_script("arguments[0].value = arguments[1];", title_input, title)
    print(f"{Fore.GREEN}Title filled: {title}{Style.RESET_ALL}")
    if config.get('manual_mode', False):
        input("Press Enter to continue after filling title...")

    # Fill tag line
    print(f"{Fore.YELLOW}Step: Filling tag line...{Style.RESET_ALL}")
    tag_line_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='tag_line']")))
    highlight_element(driver, tag_line_input)
    driver.execute_script("arguments[0].value = arguments[1];", tag_line_input, tagline)
    print(f"{Fore.GREEN}Tag line filled.{Style.RESET_ALL}")
    if config.get('manual_mode', False):
        input("Press Enter to continue after filling tag line...")

    # Fill version string
    print(f"{Fore.YELLOW}Step: Filling version string...{Style.RESET_ALL}")
    version_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='version_string']")))
    highlight_element(driver, version_input)
    driver.execute_script("arguments[0].value = arguments[1];", version_input, "1.0.0")
    print(f"{Fore.GREEN}Version set to 1.0.0.{Style.RESET_ALL}")
    if config.get('manual_mode', False):
        input("Press Enter to continue after filling version...")

    # Fill description
    print(f"{Fore.YELLOW}Step: Filling description...{Style.RESET_ALL}")
    desc_div = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.fr-element")))
    highlight_element(driver, desc_div)
    driver.execute_script("arguments[0].innerHTML = arguments[1];", desc_div, description)
    print(f"{Fore.GREEN}Description filled.{Style.RESET_ALL}")
    if config.get('manual_mode', False):
        input("Press Enter to continue after filling description...")

    # Fill tags
    print(f"{Fore.YELLOW}Step: Filling tags...{Style.RESET_ALL}")
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
    print(f"{Fore.GREEN}Tags set to {tags_text}{Style.RESET_ALL}")
    if config.get('manual_mode', False):
        input("Press Enter to continue after filling tags...")

    # Attach files
    print(f"{Fore.YELLOW}Step: Attaching files...{Style.RESET_ALL}")
    attach_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.button--icon--attach")))
    highlight_element(driver, attach_button)
    main_window = driver.current_window_handle
    driver.execute_script("arguments[0].click();", attach_button)
    print(f"{Fore.GREEN}Attach files clicked.{Style.RESET_ALL}")

    # Wait for file dialog and automate selection
    time.sleep(5)  # Wait for dialog to open
    pyautogui.write(zip_path)  # Write full path to filename field
    pyautogui.press('enter')
    print(f"{Fore.GREEN}File selected via dialog.{Style.RESET_ALL}")

    # Wait for upload completion
    print(f"{Fore.YELLOW}Step: Waiting for file upload to complete...{Style.RESET_ALL}")
    WebDriverWait(driver, config.get('upload_wait_timeout', 180)).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.file-info")))
    for i in range(wait_seconds, 0, -1):
        print(f"{Fore.CYAN}Ensuring upload completion: {i} seconds remaining...{Style.RESET_ALL}")
        time.sleep(1)
    print(f"{Fore.GREEN}File uploaded.{Style.RESET_ALL}")
    if config.get('manual_mode', False):
        input("Press Enter to continue after upload completion...")

    # Find save button
    print(f"{Fore.YELLOW}Step: Finding save button...{Style.RESET_ALL}")
    save_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[.//span[text()='Save']]")))
    highlight_element(driver, save_button)
    print(f"{Fore.GREEN}Save button found.{Style.RESET_ALL}")
    if config.get('manual_mode', False):
        input("Press Enter to continue after finding save button...")

    if config.get('auto_submit', False):
        print(f"{Fore.YELLOW}Step: Auto-submitting form...{Style.RESET_ALL}")
        submission_success = False
        for attempt in range(3):
            try:
                driver.execute_script("arguments[0].click();", save_button)
                print(f"{Fore.GREEN}Form submitted automatically.{Style.RESET_ALL}")
                WebDriverWait(driver, 30).until(lambda d: '/downloads/add' not in d.current_url)
                print(f"{Fore.GREEN}Submission successful, page redirected.{Style.RESET_ALL}")
                time.sleep(2)
                zip_path = os.path.relpath(zip_path)
                mark_processed(zip_path)
                print(f"{Fore.GREEN}Marked {zip_path} as processed.{Style.RESET_ALL}")
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
                    print(f"{Fore.YELLOW}Alert accepted, retrying submission.{Style.RESET_ALL}")
                    wait_time = (attempt + 1) * 10
                    print(f"{Fore.YELLOW}Waiting {wait_time} seconds before retry...{Style.RESET_ALL}")
                    time.sleep(wait_time)
                    continue
                except Exception as e:
                    print(f"{Fore.RED}Alert handling failed: {e}{Style.RESET_ALL}")
                    break
            except Exception as e:
                print(f"{Fore.RED}Submission failed: {e}{Style.RESET_ALL}")
                if attempt < 2:
                    wait_time = (attempt + 1) * 10
                    print(f"{Fore.YELLOW}Waiting {wait_time} seconds before retry...{Style.RESET_ALL}")
                    time.sleep(wait_time)
                    continue
                break
        if not submission_success:
            print(f"{Fore.RED}Submission failed after 3 attempts. Skipping this file.{Style.RESET_ALL}")
    else:
        highlight_element(driver, save_button)
        print(f"{Fore.CYAN}Form is ready. Press Enter in terminal to submit.{Style.RESET_ALL}")
        input()
        driver.execute_script("arguments[0].click();", save_button)
        print(f"{Fore.GREEN}Form submitted manually.{Style.RESET_ALL}")
        # Wait for successful submission
        try:
            WebDriverWait(driver, 30).until(lambda d: '/downloads/add' not in d.current_url)
            print(f"{Fore.GREEN}Submission successful, page redirected.{Style.RESET_ALL}")
            time.sleep(2)
            # Mark as processed
            zip_path = os.path.relpath(zip_path)
            mark_processed(zip_path)
            print(f"{Fore.GREEN}Marked {zip_path} as processed.{Style.RESET_ALL}")
            if shared_processed is not None:
                with shared_processed.get_lock():
                    shared_processed.value += 1
                    print_progress(shared_processed.value, shared_total.value if shared_total else 0)
        except Exception as e:
            print(f"{Fore.RED}Submission failed: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Not marking as processed.{Style.RESET_ALL}")
    
    if not shared_queue:
        print(f"{Fore.CYAN}Preparing for next upload...{Style.RESET_ALL}")
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
        print(f"{Fore.GREEN}Ready for next zip.{Style.RESET_ALL}")
    
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
    print(f"{Fore.CYAN}Processing {len(zips)} zips in this browser.{Style.RESET_ALL}")
    
    print(f"{Fore.CYAN}Starting browser...{Style.RESET_ALL}")
    options = Options()
    options.add_argument(f"user-agent={config['user_agent']}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    # options.add_argument("--headless")  # Uncomment for headless mode if needed

    print(f"{Fore.CYAN}Creating Chrome driver...{Style.RESET_ALL}")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    print(f"{Fore.GREEN}Driver created successfully.{Style.RESET_ALL}")

    try:
        print(f"{Fore.CYAN}Navigating to se7ensins.com...{Style.RESET_ALL}")
        # Navigate to the domain to add cookies
        driver.get("https://www.se7ensins.com")
        print(f"{Fore.GREEN}Navigated to se7ensins.com.{Style.RESET_ALL}")
        
        # Load cookies from any JSON file in cookies/
        print(f"{Fore.CYAN}Loading cookies...{Style.RESET_ALL}")
        cookie_files = glob.glob('cookies/*.json')
        print(f"{Fore.CYAN}Found cookie files: {cookie_files}{Style.RESET_ALL}")
        if not cookie_files:
            print(f"{Fore.YELLOW}No cookie JSON file found in cookies/{Style.RESET_ALL}")
            return
        cookie_path = cookie_files[0]  # Use the first valid JSON file
        with open(cookie_path) as f:
            cookies = json.load(f)
        print(f"{Fore.GREEN}Loaded {len(cookies)} cookies from {cookie_path}.{Style.RESET_ALL}")
        
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
        print(f"{Fore.GREEN}Cookies added to browser.{Style.RESET_ALL}")
        
        # Navigate to the target URL
        print(f"{Fore.CYAN}Navigating to {config['url']}...{Style.RESET_ALL}")
        driver.get(config['url'])
        print(f"{Fore.GREEN}Navigated to target URL.{Style.RESET_ALL}")
        
        # Wait for page to load
        print(f"{Fore.CYAN}Waiting for page to load...{Style.RESET_ALL}")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        print(f"{Fore.GREEN}Page loaded successfully.{Style.RESET_ALL}")
        
        if not config.get('skip_cloudflare', False):
            print(f"{Fore.CYAN}Page loaded. Press Enter after bypassing Cloudflare if needed.{Style.RESET_ALL}")
            input()
        else:
            print(f"{Fore.CYAN}Skipping Cloudflare bypass prompt.{Style.RESET_ALL}")
        
        if barrier:
            print(f"{Fore.CYAN}Waiting for all browsers to be ready...{Style.RESET_ALL}")
            try:
                barrier.wait(timeout=10)
                print(f"{Fore.GREEN}All browsers ready. Starting processing.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.YELLOW}Barrier timeout or error: {e}. Proceeding without sync.{Style.RESET_ALL}")
                print(f"{Fore.GREEN}All browsers ready. Starting processing.{Style.RESET_ALL}")
        
        if shared_turn is not None and turn_id is not None:
            print(f"{Fore.CYAN}Waiting for my turn ({turn_id})...{Style.RESET_ALL}")
            while shared_turn.value != turn_id:
                time.sleep(1)
            print(f"{Fore.GREEN}My turn! Processing zips.{Style.RESET_ALL}")
        
        # Automation sequence
        print(f"{Fore.CYAN}Finding Upload File button...{Style.RESET_ALL}")
        upload_button = driver.find_element(By.XPATH, "//a[@href='/downloads/add']")
        print(f"{Fore.GREEN}Upload button found.{Style.RESET_ALL}")
        highlight_element(driver, upload_button)
        print(f"{Fore.CYAN}Clicking Upload File button...{Style.RESET_ALL}")
        upload_button.click()
        print(f"{Fore.GREEN}Upload button clicked.{Style.RESET_ALL}")
        
        # Wait for category modal
        print(f"{Fore.CYAN}Waiting for category modal...{Style.RESET_ALL}")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.overlay")))
        print(f"{Fore.GREEN}Category modal appeared.{Style.RESET_ALL}")
        
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
        
        print(f"{Fore.CYAN}Available categories:{Style.RESET_ALL}")
        for i, (name, href) in enumerate(categories, 1):
            print(f"{Fore.CYAN}{i}. {name}{Style.RESET_ALL}")
        
        # Check if category_id is set in config
        if config.get('category_id') is not None:
            category_id = str(config['category_id'])
            if category_id in categories_dict:
                selected_name = categories_dict[category_id]['name']
                selected_href = categories_dict[category_id]['href']
                print(f"{Fore.GREEN}Auto-selecting category: {selected_name}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}Invalid category_id {category_id} in config. Available: {list(categories_dict.keys())}{Style.RESET_ALL}")
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
        
        print(f"{Fore.CYAN}Selecting category: {selected_name}{Style.RESET_ALL}")
        tag_to_use = config.get('tag')
        if not tag_to_use:
            tag_to_use = input("Enter the tag to use for this session: ")
        # Find the link by link text
        selected_link = driver.find_element(By.LINK_TEXT, selected_name)
        highlight_element(driver, selected_link)
        driver.execute_script("arguments[0].click();", selected_link)
        print(f"{Fore.GREEN}Category selected.{Style.RESET_ALL}")
        
        # Wait for category modal to close
        print(f"{Fore.CYAN}Waiting for category modal to close...{Style.RESET_ALL}")
        WebDriverWait(driver, 10).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.overlay")))
        print(f"{Fore.GREEN}Category modal closed.{Style.RESET_ALL}")
        
        # Wait for upload form
        print(f"{Fore.CYAN}Waiting for upload form...{Style.RESET_ALL}")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "title")))
        print(f"{Fore.GREEN}Upload form loaded.{Style.RESET_ALL}")
        
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
                print(f"{Fore.CYAN}Processing {i}/{len(zips)} : {os.path.basename(zip_path)}{Style.RESET_ALL}")
                process_single_zip(zip_path, driver, config, lock, tag_to_use, shared_processed, shared_total, shared_queue, shared_turn, num_browsers, selected_name)
        
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        print(f"{Fore.RED}Full traceback:{Style.RESET_ALL}")
        traceback.print_exc()
    finally:
        print(f"{Fore.CYAN}Closing browser...{Style.RESET_ALL}")
        driver.quit()
        print(f"{Fore.GREEN}Browser closed.{Style.RESET_ALL}")

def main():
    config = load_config()
    init_db()
    num_browsers = config.get('num_browsers', 1)
    
    # Pre-install ChromeDriver to avoid conflicts in multiprocessing
    ChromeDriverManager().install()
    
    all_zips = [z for z in glob.glob('zipsToUpload/*.zip') if not is_processed(z)]
    if not all_zips:
        print(f"{Fore.YELLOW}No zips to process.{Style.RESET_ALL}")
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
                print(f"{Fore.YELLOW}waiting 10 seconds between browser windows to avoid pissing off Cloudflare...{Style.RESET_ALL}")
                time.sleep(10)
        
        for p in processes:
            p.join()

if __name__ == "__main__":
    main()