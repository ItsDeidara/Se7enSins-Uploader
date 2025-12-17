# Se7enSins Uploader

A Selenium bot for automating uploads to the Se7enSins download center, supporting cookie import, multi-browser operation, category selection, form filling, and file uploads.

## Prerequisites

- Python 3.7 or higher
- Google Chrome browser installed
- Exported cookies from your Se7enSins session
- a Premium Se7enSins account or adblocker because full screen ads will break this bot. This can still occasionaly happen if ads load before cookies are injected

## Setup

1. Clone or download this project to your local machine.

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Export your cookies from the browser and place them in the `cookies/` folder (see below).

4. Place your zip files to upload in the `zipsToUpload/` folder. Each zip should contain a README.md file with the description and tagline.

5. Update `config.json` with your settings (see Configuration section).

## Exporting Cookies

To authenticate with Se7enSins, you need to export your session cookies:

1. Log in to https://www.se7ensins.com in your browser.

2. Use a browser extension like "Export Cookies" (for Chrome) or "Cookie Editor" (cross-browser).

3. Export cookies for the domain `www.se7ensins.com` or `.se7ensins.com` as JSON format.

4. Save the JSON file in the `cookies/` folder (e.g., `cookies/my_cookies.json`).

The bot will automatically detect and load any valid JSON cookie file from the `cookies/` folder. If a file named `cookies/{site}.json` exists (for example `cookies/gbatemp.json` when `site` is set to `gbatemp` in `config.json`), it will be preferred. To target GBAtemp, set `site` to `gbatemp` and `url` to `https://gbatemp.net/download/`, and place your cookies in `cookies/gbatemp.json`.

## Configuration

Edit `config.json` to customize the bot:

- `user_agent`: A string representing the browser user agent. Use an up-to-date one for compatibility. Up-to-date user agents can be found at https://useragents.io/. Example: `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"`

- `url`: The URL to navigate to initially (default: `"https://www.se7ensins.com/downloads/"`).

- `num_browsers`: Number of browser instances to run in parallel (default: `1`). Useful for distributing upload tasks across multiple sessions.

- `auto_submit`: Whether to automatically click the save button after filling the form (default: `false` for testing).

- `skip_cloudflare`: Whether to skip the manual Cloudflare bypass prompt (default: `true`).

- `category_id`: The ID of the category to select automatically (from `categories.json`), e.g., `3` for "Xbox (Original)". Set to `null` to prompt for manual selection.

- `tag`: The tag to apply to all uploads in this session. Set to `null` to prompt for manual entry.

Note: `categories.json` is automatically generated when the category selection modal loads for the first time. If categories are added, removed, or changed on the site, simply delete `categories.json` to regenerate it on the next run.

The bot will automatically process all zip files in `zipsToUpload/` that haven't been uploaded yet, tracking progress in a local database (`progress.db`) to allow resuming interrupted uploads.

## Running the Bot

1. Ensure at least one valid cookie JSON file is in the `cookies/` folder.

2. Open a terminal in the project directory.

3. Run the bot:
   ```
   python main.py
   ```

### GUI

A simple dark-mode GUI is included to edit `config.json` in real time and to run uploads directly from the GUI (standalone) without invoking the CLI `main.py`.

The GUI also supports importing `categories.json` (or will load an existing one) so you can select the upload category directly in the GUI — selecting a category sets `category_id` in `config.json`.

Changes made in the GUI are written immediately to `config.json` and the GUI picks them up at runtime (tags, upload timing, auto-submit, skip-cloudflare, category selection, etc.).

Start the GUI with:
```bash
python GUI.py
```

4. The bot will:
   - Launch Chrome with the specified user agent and stealth options.
   - Navigate to https://www.se7ensins.com to set the domain.
   - Load and inject the cookies from the JSON file.
   - Navigate to the configured URL.
   - Wait for the page to fully load.

5. If Cloudflare protection triggers and `skip_cloudflare` is false, manually solve the captcha.

6. The bot will scrape available categories and save to `categories.json`.

7. If `category_id` is set, auto-select the category; otherwise, prompt for selection.

8. If `tag` is set, use it for all uploads; otherwise, prompt for the tag.

9. For each unprocessed zip in `zipsToUpload/`:
   - Extract title from zip name.
   - Extract tagline and description from README.md in the zip.
   - Fill the upload form.
   - Upload the file using PyAutoGUI to handle the file dialog.
   - Fill tags.
   - Submit if `auto_submit` is true.

9. Progress is tracked in `progress.db` for resumability.

For multiple browsers (`num_browsers` > 1), each instance runs in a separate process, allowing parallel operation.

## How It Works

- **Cookie Injection**: Cookies are added to the browser session to maintain your login state.
- **Page Loading**: Uses Selenium's WebDriverWait to ensure the page is fully loaded before proceeding.
- **Category Selection**: Scrapes categories on first run, allows auto-selection via config.
- **Form Filling**: Automatically fills title, tagline, description, tags, and uploads files.
- **File Upload**: Uses PyAutoGUI to interact with the Windows file dialog.
- **Progress Tracking**: SQLite database tracks processed zips.
- **Multi-Browser Support**: Uses Python's multiprocessing to run independent browser instances.

## Troubleshooting

- **No cookie file found**: Ensure a valid JSON file is in `cookies/`. Check the file format.
- **Browser doesn't load**: Update the user agent in `config.json`.
- **Cloudflare blocks**: Manually bypass or set `skip_cloudflare` to true.
- **Selenium errors**: Ensure Chrome is installed and up-to-date. webdriver-manager handles ChromeDriver.
- **Multiple cookie files**: The bot prefers a file named `cookies/{site}.json` (e.g., `cookies/gbatemp.json`), otherwise it uses the first JSON file found alphabetically.
- **File upload fails**: Ensure PyAutoGUI can interact with the dialog; may need to adjust timings.
- **Category not found**: Run once to generate `categories.json`, then set `category_id`.
- **Tags not filling**: Ensure the Tagify component is loaded; the bot targets the input span. Set `tag` in config or enter manually when prompted.

## Dependencies

- selenium: For web automation.
- webdriver-manager: For automatic ChromeDriver management.
- pyautogui: For file dialog automation.
- colorama: For colored terminal output.