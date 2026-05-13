# Nodriver MCP Server

This MCP server provides browser automation for job applications, LinkedIn
research, recruiter/contact discovery, and logged-in web workflows. It uses
`nodriver` to control Chrome, inspect pages, interact with forms, capture
screenshots, and debug dynamic application sites.

## Intended Use

- Navigate job boards, company career pages, and LinkedIn
- Fill and inspect application forms with a visible signed-in browser
- Capture screenshots, page source, accessibility trees, and console logs
- Watch network activity for dynamic applicant portals such as Greenhouse,
  Lever, Workday, Ashby, and LinkedIn
- Reuse a persistent Chrome session so existing logins stay available

## Browser Configuration

The browser starts in Google Chrome using the local signed-in Ben profile:

- Account: `bendov1010@gmail.com`
- Chrome profile directory: `Profile 1`
- User data dir: `$HOME/Library/Application Support/Google/Chrome`
- Chrome binary: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`

You can override the local profile without editing code:

```bash
export NODRIVER_CHROME_USER_DATA_DIR="$HOME/Library/Application Support/Google/Chrome"
export NODRIVER_CHROME_PROFILE_DIRECTORY="Profile 1"
export NODRIVER_CHROME_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

The server defaults to a visible browser because application portals and
LinkedIn flows often need an already signed-in, human-observable session.

## Scope Guard

This copy is configured for applications and LinkedIn work. It blocks navigation
to known gambling/sportsbook domains by default so old source-project behavior
does not leak into recruiting workflows.

Only override this guard intentionally:

```bash
export NODRIVER_ALLOW_GAMBLING_URLS=1
```

## Core Workflow

1. Start a persistent browser session:
   `start_browser(headless=false)`
2. Navigate to the target application or LinkedIn page:
   `navigate(url="https://www.linkedin.com/jobs/")`
3. Inspect the page:
   `get_accessibility_tree()`, `get_cleaned_html()`, or `take_screenshot()`
4. Interact with forms:
   `click_element()`, `human_click()`, `type_text()`, `select_option()`
5. Wait for dynamic content:
   `wait_for_network_idle(timeout=5, idle_time=1)`
6. Use network tools only when needed:
   `start_network_interception()`, `get_network_summary()`,
   `save_network_responses()`
7. Keep the session open while working through related pages, then call
   `stop_browser()` when done.

## Available Tools

### Browser Control

- `start_browser` - Start the Chrome session with the configured profile
- `stop_browser` - Stop the browser session
- `navigate` - Navigate to an allowed URL
- `refresh_page` - Reload the current page
- `set_device_mode` - Switch between mobile and desktop emulation

### Element Interaction

- `click_element` - Click elements by CSS selector
- `human_click` - Click with mouse movement and randomized target position
- `type_text` - Type text with realistic keystroke delays
- `select_option` - Select dropdown options and fire change events
- `wait_for_element` - Wait for an element to appear
- `scroll_page` - Human-like scrolling with pauses and variable speeds
- `press_and_hold` - Hold a mouse press at coordinates for challenge widgets

### Page Inspection

- `get_page_source` - Get current page HTML
- `get_cleaned_html` - Get simplified HTML without scripts/styles
- `get_accessibility_tree` - Get an AI-friendly element map
- `take_screenshot` - Capture the current page
- `read_console_logs` - Read browser console messages
- `execute_javascript` - Run JavaScript on the current page
- `execute_cdp_command` - Run a Chrome DevTools Protocol command

### Network And Session

- `start_network_interception` - Begin capturing network traffic
- `stop_network_interception` - Stop capturing network traffic
- `get_network_events` - Retrieve captured requests and responses
- `get_network_summary` - Summarize captured network activity
- `save_network_responses` - Save captured responses to JSON files
- `analyze_network_responses` - Run local Python analysis on saved responses
- `verify_curl` - Test a captured request in browser context
- `start_websocket_interception` - Capture WebSocket frames
- `stop_websocket_interception` - Stop WebSocket capture
- `get_websocket_frames` - Retrieve captured WebSocket messages
- `save_cookies` - Save cookies for session persistence
- `load_cookies` - Restore cookies

## Installation

```bash
cd mcp/nodriver_server
pip install -e .
```

## Running The Server

```bash
python -m nodriver_server.server
```

Or from the repo-level wrapper:

```bash
python mcp/run_nodriver_mcp.py
```
