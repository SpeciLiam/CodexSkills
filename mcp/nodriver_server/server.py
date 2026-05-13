#!/usr/bin/env python3
"""
!!! AI ASSISTANT WARNING !!!
DO NOT IMPORT FROM THIS FILE.
DO NOT ATTEMPT TO CALL FUNCTIONS IN THIS FILE DIRECTLY.

This is a standalone MCP Server.
- You MUST use the MCP Tools provided by this server (e.g., call_tool("start_browser")).
- You CANNOT import 'server.py' or its functions.
- If you try to `from server import ...`, the code will fail.
- Functions in this file are PRIVATE and for MCP server use only.

MCP Server for nodriver-based browser automation.

This server provides AI agents with tools to:
- Navigate to websites and interact with elements
- Intercept and analyze network requests/responses
- Take screenshots and inspect HTML
- Work through job applications, LinkedIn research, and logged-in web workflows

Based on the orchestrator/browser_orchestrator.py functionality.
"""

import asyncio
import json
import logging
import os
import random
import sys
import traceback
from typing import Any, Dict, List, Optional, Sequence, Union
from datetime import datetime
from urllib.parse import urlparse

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
  Resource,
  Tool,
  TextContent,
  ImageContent,
  EmbeddedResource,
  LoggingLevel
)

import nodriver as driver
from nodriver import cdp
from typing import cast


# Ensure project root on path for imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
  sys.path.insert(0, project_root)


logger = logging.getLogger("nodriver_mcp_server")

DEFAULT_CHROME_USER_DATA_DIR = os.path.expanduser(
  "~/Library/Application Support/Google/Chrome"
)
DEFAULT_CHROME_PROFILE_DIRECTORY = "Profile 1"
DEFAULT_CHROME_PROFILE_EMAIL = "bendov1010@gmail.com"
DEFAULT_CHROME_EXECUTABLE_PATH = (
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
GAMBLING_DOMAIN_PARTS = (
  "bet365",
  "betano",
  "betfair",
  "betmgm",
  "betonline",
  "betparx",
  "betrivers",
  "caesars",
  "draftkings",
  "espnbet",
  "fanduel",
  "fanaticsbook",
  "hardrock.bet",
  "pinnacle",
  "pointsbet",
  "sportsbook",
  "williamhill",
)


def get_chrome_profile_config() -> Dict[str, Optional[str]]:
  """Return the local Chrome profile settings used for signed-in MCP sessions."""
  user_data_dir = os.path.expanduser(
    os.environ.get("NODRIVER_CHROME_USER_DATA_DIR", DEFAULT_CHROME_USER_DATA_DIR)
  )
  profile_directory = os.environ.get(
    "NODRIVER_CHROME_PROFILE_DIRECTORY", DEFAULT_CHROME_PROFILE_DIRECTORY
  )
  executable_path = os.environ.get(
    "NODRIVER_CHROME_EXECUTABLE_PATH", DEFAULT_CHROME_EXECUTABLE_PATH
  )

  if not os.path.isdir(user_data_dir):
    logger.warning(
      "Chrome user data dir %s does not exist; nodriver will create/use its default profile",
      user_data_dir,
    )
    user_data_dir = None

  if executable_path and not os.path.exists(executable_path):
    logger.warning(
      "Chrome executable %s does not exist; nodriver will auto-detect a browser",
      executable_path,
    )
    executable_path = None

  return {
    "user_data_dir": user_data_dir,
    "profile_directory": profile_directory,
    "executable_path": executable_path,
    "profile_email": os.environ.get(
      "NODRIVER_CHROME_PROFILE_EMAIL", DEFAULT_CHROME_PROFILE_EMAIL
    ),
  }


def ensure_allowed_url(url: str) -> None:
  """Prevent this application-focused MCP from navigating to sportsbook domains."""
  if os.environ.get("NODRIVER_ALLOW_GAMBLING_URLS") == "1":
    return

  parsed = urlparse(url)
  hostname = (parsed.hostname or "").lower()
  if not hostname:
    return

  if any(domain_part in hostname for domain_part in GAMBLING_DOMAIN_PARTS):
    raise ValueError(
      f"Blocked gambling/sportsbook URL for application-focused MCP: {hostname}. "
      "Set NODRIVER_ALLOW_GAMBLING_URLS=1 only if you intentionally need this."
    )


class BrowserSession:
  """Manages a single browser session with nodriver."""

  def __init__(self):
    self.browser: Optional[driver.Browser] = None
    self.current_tab: Optional[driver.Tab] = None
    self.current_frame: Optional[Any] = None
    self.network_events: List[Dict[str, Any]] = []
    self.intercepting = False
    # WebSocket interception
    self.websocket_frames: List[Dict[str, Any]] = []
    self.websocket_connections: Dict[str, Dict[str, Any]] = {}
    self.ws_intercepting = False

  async def start_browser(self, headless: bool = False) -> None:
    """Start the browser instance with stealth configuration."""
    if self.browser:
      return

    chrome_profile = get_chrome_profile_config()
    logger.info(
      "Starting Chrome with dark mode, fullscreen, and profile %s (%s)...",
      chrome_profile["profile_directory"],
      chrome_profile["profile_email"],
    )

    # Essential browser arguments for dark mode, fullscreen, and stealth
    args = [
        f"--profile-directory={chrome_profile['profile_directory']}",

        # Dark mode and appearance
        "--force-dark-mode",
        "--enable-features=WebContentsForceDark:inversion_method/cielab_based/image_behavior/0",
        "--dark-mode-settings=EnableDarkMode",

        # Window management - always maximize
        "--start-maximized",
        "--window-size=1920,1080",  # Fallback size

        # Anti-detection and performance
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-infobars",
        "--disable-extensions",
        "--disable-plugins",
        "--disable-default-apps",
        "--disable-sync",
        "--disable-translate",
        "--hide-scrollbars",
        "--metrics-recording-only",
        "--no-first-run",
        "--safebrowsing-disable-auto-update",
        "--disable-component-extensions-with-background-pages",

        # Performance and stability
        "--disable-dev-shm-usage",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=VizDisplayCompositor",
        "--disable-ipc-flooding-protection",
        "--disable-hang-monitor",
        "--disable-prompt-on-repost",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-client-side-phishing-detection",
        "--disable-background-networking",
    ]

    # Short retry/backoff around start to handle occasional CDP race conditions
    last_err = None
    for attempt in range(3):
      try:
        self.browser = await driver.start(
            headless=headless,
            user_data_dir=chrome_profile["user_data_dir"],
            browser_executable_path=chrome_profile["executable_path"],
            browser_args=args,
            lang="en-US"
        )
        logger.info("Browser started successfully in dark mode")
        last_err = None
        break
      except Exception as e:
        last_err = e
        logger.warning(f"Browser start attempt {attempt + 1} failed: {e}")
        if attempt < 2:
          await asyncio.sleep(1.0 * (attempt + 1))
        else:
          logger.error(f"Failed to start browser after 3 attempts: {last_err}")
          raise last_err

  async def stop_browser(self) -> None:
    """Stop the browser instance."""
    if self.browser:
      logger.info("Stopping browser...")
      try:
        stop_method = getattr(self.browser, 'stop', None)
        if stop_method is not None:
          if asyncio.iscoroutinefunction(stop_method):
            await stop_method()
          else:
            # Handle sync stop methods
            await asyncio.to_thread(stop_method)
      except Exception as e:
        logger.error(f"Error stopping browser: {e}")
      finally:
        self.browser = None
        self.current_tab = None

  async def new_tab(self, url: str = "about:blank") -> driver.Tab:
    """Create a new tab and navigate to URL."""
    if not self.browser:
      raise RuntimeError("Browser not started")
    ensure_allowed_url(url)

    logger.info(f"Creating new tab with URL: {url}")
    self.current_tab = await self.browser.get(url, new_tab=True)
    return self.current_tab

  async def close_current_tab(self) -> None:
    """Close the current tab."""
    if self.current_tab:
      await self.current_tab.close()
      self.current_tab = None

  async def navigate(self, url: str) -> None:
    """Navigate to a URL."""
    ensure_allowed_url(url)
    logger.info(f"Navigating to: {url}")
    try:
      # If we have an existing tab, navigate in place to keep handlers
      if self.current_tab:
        await asyncio.wait_for(
          self.current_tab.get(url),
          timeout=15.0
        )
      else:
        # Create new tab if none exists
        self.current_tab = await asyncio.wait_for(
          self.browser.get(url, new_tab=True),
          timeout=15.0
        )
    except asyncio.TimeoutError:
      logger.error(f"Navigation to {url} timed out")
      raise RuntimeError(f"Navigation to {url} timed out after 15 seconds")
    except Exception as e:
      logger.error(f"Navigation failed: {e}")
      raise

  async def get_page_source(self) -> str:
    """Get the current page HTML source."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    return await self.current_tab.get_content()

  async def click_element(self, selector: str, timeout: int = 10) -> None:
    """Click an element by CSS selector."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    logger.info(f"Clicking element: {selector}")
    element = await self.current_tab.select(selector, timeout=timeout)
    if element:
      await element.click()
    else:
      raise ValueError(f"Element not found: {selector}")

  async def wait_for_element(self, selector: str, timeout: int = 10) -> None:
    """Wait for an element to appear."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    logger.info(f"Waiting for element: {selector}")
    await self.current_tab.select(selector, timeout=timeout)

  async def execute_javascript(self, script: str) -> Any:
    """Execute JavaScript in the current tab."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    logger.info("Executing JavaScript")

    # For simple expressions without return, execute directly
    # For expressions with return, wrap in a function
    if script.strip().startswith('return '):
      # Wrap return statements in a function
      wrapped_script = f"(function() {{ {script} }})()"
    else:
      wrapped_script = script

    try:
      # Add timeout to prevent hanging
      result = await asyncio.wait_for(
        self.current_tab.evaluate(wrapped_script),
        timeout=10.0  # 10 second timeout
      )
      return result
    except asyncio.TimeoutError:
      logger.error("JavaScript execution timed out")
      raise RuntimeError("JavaScript execution timed out after 10 seconds")
    except Exception as e:
      logger.error(f"JavaScript execution failed: {e}")
      raise

  async def take_screenshot(self) -> str:
    """Take a screenshot of the current page. Returns base64-encoded PNG string."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    logger.info("Taking screenshot")
    # Use CDP command for screenshot since nodriver Tab doesn't have screenshot method
    result = await self.current_tab.send(cdp.page.capture_screenshot(format_="png"))
    # result is already a base64 string (or tuple where first element is the string)
    if isinstance(result, tuple):
      return result[0]
    return result

  async def get_accessibility_tree(self) -> str:
    """Returns a simplified text structure of the page for the AI."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    # This JS script extracts key interactive elements
    js = """
    (() => {
        function describe(node) {
            const role = node.getAttribute('role') || node.tagName.toLowerCase();
            const label = node.innerText || node.getAttribute('aria-label') || node.getAttribute('placeholder') || '';
            const visible = node.checkVisibility();
            if (!visible || !label) return null;
            return `[${role}] ${label.trim().substring(0, 50)}`;
        }

        // Select all potentially interesting elements
        const elements = document.querySelectorAll('button, a, input, select, [role="button"], h1, h2, h3, .outcome-cell, .odd-value');
        return Array.from(elements)
            .map(describe)
            .filter(x => x)
            .join('\\n');
    })()
    """
    result = await self.current_tab.evaluate(js)
    return str(result) if result is not None else ""

  async def save_cookies(self, filepath: str = "cookies.json") -> None:
    """Save current browser cookies to a JSON file."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    try:
      # Get all cookies for the current domain
      cookies_resp = await self.current_tab.send(cdp.network.get_cookies())
      cookie_data = {}

      for cookie in cookies_resp.cookies:
        key = f"{cookie.domain}{cookie.path}{cookie.name}"
        cookie_data[key] = {
          "name": cookie.name,
          "value": cookie.value,
          "domain": cookie.domain,
          "path": cookie.path,
          "secure": cookie.secure,
          "httpOnly": cookie.http_only,
          "sameSite": cookie.same_site,
          "expires": cookie.expires
        }

      import json
      with open(filepath, 'w') as f:
        json.dump(cookie_data, f, indent=2)
      logger.info(f"Cookies saved to {filepath}")
    except Exception as e:
      logger.error(f"Failed to save cookies: {e}")
      raise

  async def load_cookies(self, filepath: str = "cookies.json") -> None:
    """Load cookies from a JSON file into the browser."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    try:
      import json
      with open(filepath, 'r') as f:
        cookie_data = json.load(f)

      for cookie_info in cookie_data.values():
        try:
          # Set cookie using network domain
          await self.current_tab.send(cdp.network.set_cookie(
            name=cookie_info["name"],
            value=cookie_info["value"],
            domain=cookie_info["domain"],
            path=cookie_info.get("path", "/"),
            secure=cookie_info.get("secure", False),
            http_only=cookie_info.get("httpOnly", False),
            same_site=cookie_info.get("sameSite", "Lax"),
            expires=cookie_info.get("expires")
          ))
        except Exception as e:
          logger.warning(f"Failed to set cookie {cookie_info.get('name', 'unknown')}: {e}")

      logger.info(f"Cookies loaded from {filepath}")
    except FileNotFoundError:
      logger.warning(f"Cookie file {filepath} not found")
    except Exception as e:
      logger.error(f"Failed to load cookies: {e}")
      raise

  async def wait_for_network_idle(self, timeout: int = 10, idle_time: int = 2) -> None:
    """Wait for network activity to become idle (no requests for idle_time seconds)."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    logger.info(f"Waiting for network idle (timeout: {timeout}s, idle time: {idle_time}s)")

    start_time = asyncio.get_event_loop().time()
    last_request_time = start_time

    # Track when the last network request was made
    def on_any_request(*args, **kwargs):
      nonlocal last_request_time
      last_request_time = asyncio.get_event_loop().time()

    # Listen for network events
    self.current_tab.add_handler(cdp.network.RequestWillBeSent, on_any_request)

    try:
      while True:
        current_time = asyncio.get_event_loop().time()
        elapsed = current_time - start_time

        if elapsed > timeout:
          logger.warning(f"Network idle timeout after {timeout}s")
          break

        # Check if we've had idle_time seconds without network activity
        if current_time - last_request_time >= idle_time:
          logger.info(f"Network idle detected after {elapsed:.1f}s")
          break

        await asyncio.sleep(0.5)  # Check every 500ms

    finally:
      # Clean up the handler
      try:
        self.current_tab.remove_handler(cdp.network.RequestWillBeSent, on_any_request)
      except Exception:
        pass

  async def type_text(self, selector: str, text: str, delay_range: Optional[List[int]] = None) -> None:
    """Type text into an element with human-like delays between keystrokes."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    if delay_range is None:
      delay_range = [50, 200]  # Default: 50-200ms between keystrokes

    # Use JavaScript to simulate human typing
    escaped_text = text.replace("'", "\\'").replace("\n", "\\n").replace("\t", "\\t")
    js_script = f"""
    (async () => {{
      const element = document.querySelector('{selector}');
      if (!element) return false;

      element.focus();
      element.click();

      const text = '{escaped_text}';
      for (let i = 0; i < text.length; i++) {{
        const char = text[i];
        const delay = Math.random() * ({delay_range[1]} - {delay_range[0]}) + {delay_range[0]};
        await new Promise(resolve => setTimeout(resolve, delay));

        // Simulate typing by setting value and dispatching events
        element.value += char;
        const event = new Event('input', {{ bubbles: true }});
        element.dispatchEvent(event);
      }}
      return true;
    }})();
    """

    result = await self.current_tab.evaluate(js_script)
    if not result:
      raise ValueError(f"Element not found: {selector}")

  async def select_option(self, selector: str, value: str) -> None:
    """Select an option from a dropdown and fire change event."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    # Click the dropdown first
    dropdown = await self.current_tab.select(selector)
    if not dropdown:
      raise ValueError(f"Dropdown not found: {selector}")

    await dropdown.click()

    # Wait a bit for options to appear
    await asyncio.sleep(0.5)

    # Try to find and click the option
    option_selector = f'option[value="{value}"], [data-value="{value}"], [value="{value}"]'
    option = await self.current_tab.select(option_selector)
    if option:
      await option.click()
    else:
      # Try a broader selector for custom dropdowns
      option_selector = f'*[contains(text(), "{value}")]'
      option = await self.current_tab.select(option_selector)
      if option:
        await option.click()
      else:
        raise ValueError(f"Option not found: {value}")

    # Fire change event via JavaScript
    change_script = f"""
    const element = document.querySelector('{selector}');
    if (element) {{
      element.value = '{value}';
      element.dispatchEvent(new Event('change', {{bubbles: true}}));
      element.dispatchEvent(new Event('input', {{bubbles: true}}));
    }}
    """
    await self.current_tab.evaluate(change_script)

  async def switch_to_frame(self, frame_selector: str) -> None:
    """Switch context to an iframe."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    # Find the iframe element
    frame_element = await self.current_tab.select(frame_selector)
    if not frame_element:
      raise ValueError(f"Frame not found: {frame_selector}")

    # Type assertion: we know frame_element is not None after the check
    assert frame_element is not None

    # Get frame's content document
    if (frame_doc := await frame_element.get_content_document()) is not None:
      # Switch to the frame's document
      self.current_frame = frame_doc
      logger.info(f"Switched to frame: {frame_selector}")
    else:
      raise RuntimeError(f"Could not access frame content: {frame_selector}")

  async def execute_in_frame(self, frame_selector: str, script: str) -> Any:
    """Execute JavaScript inside a specific iframe."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    frame_element = await self.current_tab.select(frame_selector)
    if not frame_element:
      raise ValueError(f"Frame not found: {frame_selector}")

    # Type assertion: we know frame_element is not None after the check
    assert frame_element is not None

    if (frame_doc := await frame_element.get_content_document()) is not None:
      return await frame_doc.evaluate(script)
    else:
      raise RuntimeError(f"Could not access frame content: {frame_selector}")

  async def set_device_mode(self, mobile: bool = True) -> None:
    """Emulate mobile or desktop device."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    if mobile:
      # iPhone 14 emulation
      await self.current_tab.send(cdp.emulation.set_user_agent_override(
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
      ))
      await self.current_tab.send(cdp.emulation.set_device_metrics_override(
        width=390,
        height=844,
        device_scale_factor=3.0,
        mobile=True,
        screen_width=390,
        screen_height=844
      ))
    else:
      # Reset to desktop
      await self.current_tab.send(cdp.emulation.clear_device_metrics_override())

    logger.info(f"Set device mode: {'mobile' if mobile else 'desktop'}")

  async def read_console_logs(self, level: str = "error") -> List[Dict[str, Any]]:
    """Read browser console logs."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    logs = []

    def on_console_message(event):
      if hasattr(event, 'level') and event.level == level:
        logs.append({
          "level": event.level,
          "message": event.message,
          "timestamp": datetime.now().isoformat()
        })

    # Listen for console events
    self.current_tab.add_handler(cdp.runtime.ConsoleAPICalled, on_console_message)

    # Wait a moment to collect logs
    await asyncio.sleep(1.0)

    # Clean up handler
    try:
      self.current_tab.remove_handler(cdp.runtime.ConsoleAPICalled, on_console_message)
    except Exception:
      pass

    return logs

  async def get_cleaned_html(self) -> str:
    """Get HTML with scripts, styles, and images removed for token savings."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    # Get raw HTML
    html = await self.current_tab.get_content()

    # Remove unwanted elements using JavaScript
    clean_script = """
    function cleanHTML(html) {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');

      // Remove script tags
      const scripts = doc.querySelectorAll('script');
      scripts.forEach(s => s.remove());

      // Remove style tags
      const styles = doc.querySelectorAll('style');
      styles.forEach(s => s.remove());

      // Remove SVG tags
      const svgs = doc.querySelectorAll('svg');
      svgs.forEach(s => s.remove());

      // Remove img tags
      const imgs = doc.querySelectorAll('img');
      imgs.forEach(i => i.remove());

      return doc.documentElement.outerHTML;
    }

    return cleanHTML(arguments[0]);
    """

    try:
      cleaned_html = await self.current_tab.evaluate(clean_script, html)
      return str(cleaned_html) if cleaned_html else html
    except Exception:
      # Fallback to original HTML if cleaning fails
      return html

  async def verify_curl(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Verify if a captured request works by testing it in browser context."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    if headers is None:
      headers = {}

    # Convert headers dict to fetch Headers object format
    headers_js = ", ".join(f'"{k}": "{v}"' for k, v in headers.items())

    verify_script = f"""
    (async () => {{
      try {{
        const response = await fetch("{url}", {{
          method: "GET",
          headers: {{
            {headers_js}
          }}
        }});

        const status = response.status;
        const statusText = response.statusText;
        const ok = response.ok;

        let body = null;
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {{
          body = await response.text();
        }}

        return {{
          success: true,
          status: status,
          statusText: statusText,
          ok: ok,
          contentType: contentType,
          bodyLength: body ? body.length : 0
        }};
      }} catch (error) {{
        return {{
          success: false,
          error: error.message
        }};
      }}
    }})();
    """

    result = await self.current_tab.evaluate(verify_script)
    return result if isinstance(result, dict) else {"success": False, "error": "Invalid response"}

  async def human_click(self, selector: str, hover: bool = True, hover_delay: Optional[List[float]] = None) -> None:
    """Perform a human-like click by moving mouse to random position within element."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    if hover_delay is None:
      hover_delay = [0.5, 1.5]

    element = await self.current_tab.select(selector)
    if not element:
      raise ValueError(f"Element not found: {selector}")

    # Type assertion: we know element is not None after the check
    assert element is not None

    # Get the element's bounding box
    if (quads := await element.get_content_quads()) is None or len(quads) == 0:
      raise RuntimeError("Element has no coordinates (invisible?)")

    box = quads[0]

    # Calculate bounds
    x_coords = [box[0], box[2], box[4], box[6]]
    y_coords = [box[1], box[3], box[5], box[7]]

    min_x, max_x = min(x_coords), max(x_coords)
    min_y, max_y = min(y_coords), max(y_coords)

    # Pick a random point within the element (with padding)
    padding = 5
    target_x = random.uniform(min_x + padding, max_x - padding)
    target_y = random.uniform(min_y + padding, max_y - padding)

    # Handle high-DPI screens
    js_dpr_raw = await self.current_tab.evaluate("window.devicePixelRatio")
    dpr: float = 1.0
    if js_dpr_raw is not None:
      try:
        # Type check: ensure it's a number-like value
        if isinstance(js_dpr_raw, (int, float, str)):
          dpr = float(js_dpr_raw)
        else:
          dpr = 1.0
      except (TypeError, ValueError):
        dpr = 1.0
    target_x = target_x / dpr
    target_y = target_y / dpr

    # Use JavaScript for human-like clicking to avoid CDP API issues
    js_click = f"""
    (async () => {{
      const element = document.querySelector('{selector}');
      if (!element) return false;

      const rect = element.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      // Create mouse events at random position within element
      const padding = 5;
      const randomX = centerX + (Math.random() - 0.5) * (rect.width - 2 * padding);
      const randomY = centerY + (Math.random() - 0.5) * (rect.height - 2 * padding);

      // Move mouse to position
      const moveEvent = new MouseEvent('mousemove', {{
        clientX: randomX,
        clientY: randomY,
        bubbles: true
      }});
      document.dispatchEvent(moveEvent);

      // Wait for hover
      await new Promise(resolve => setTimeout(resolve, {int(hover_delay[0] * 1000)}));

      // Click
      const downEvent = new MouseEvent('mousedown', {{
        clientX: randomX,
        clientY: randomY,
        button: 0,
        bubbles: true
      }});
      element.dispatchEvent(downEvent);

      await new Promise(resolve => setTimeout(resolve, 50));

      const upEvent = new MouseEvent('mouseup', {{
        clientX: randomX,
        clientY: randomY,
        button: 0,
        bubbles: true
      }});
      element.dispatchEvent(upEvent);

      const clickEvent = new MouseEvent('click', {{
        clientX: randomX,
        clientY: randomY,
        button: 0,
        bubbles: true
      }});
      element.dispatchEvent(clickEvent);

      return true;
    }})();
    """

    result = await self.current_tab.evaluate(js_click)
    if not result:
      raise ValueError(f"Element not found: {selector}")

    logger.info(f"Human click performed on: {selector}")

  async def human_scroll(self, direction: str = "down", distance: Optional[int] = None,
                        max_scrolls: Optional[int] = None, element_selector: Optional[str] = None) -> str:
    """
    Scrolls the page or element like a human: variable speeds, pauses to 'read',
    and uses the mouse wheel protocol instead of JS.

    Args:
        direction: "down", "up", "left", "right"
        distance: Total pixels to scroll (approximate). If None, scrolls random amount.
        max_scrolls: Maximum number of scroll bursts. If None, scrolls until distance reached.
        element_selector: If provided, scrolls within this element instead of page
    """
    if not self.current_tab:
      raise RuntimeError("No active tab")

    if not distance:
      distance = random.randint(800, 1500)

    # Calculate scroll deltas based on direction
    if direction in ["down", "up"]:
      delta_x = 0
      delta_y = 120 if direction == "down" else -120
    elif direction in ["left", "right"]:
      delta_x = 120 if direction == "right" else -120
      delta_y = 0
    else:
      raise ValueError(f"Invalid direction: {direction}. Use 'up', 'down', 'left', 'right'")

    current_scroll = 0
    scroll_count = 0
    max_scrolls = max_scrolls or 50  # Safety limit

    while current_scroll < distance and scroll_count < max_scrolls:
      # 1. Scroll in a "burst" (simulating one finger flick)
      burst_length = random.randint(2, 5)  # 2-5 wheel notches per burst

      for burst_step in range(burst_length):
        # Jitter the scroll amount (humans aren't perfect)
        jitter_x = random.randint(-15, 15) if direction in ["left", "right"] else 0
        jitter_y = random.randint(-15, 15) if direction in ["up", "down"] else 0

        scroll_x = delta_x + jitter_x
        scroll_y = delta_y + jitter_y

        # Position mouse randomly on page/element
        if element_selector:
          # Get element bounds for targeted scrolling
          element_selector_json = json.dumps(element_selector)
          element_bounds = await self.current_tab.evaluate(f"""
            const el = document.querySelector({element_selector_json});
            if (el) {{
              const rect = el.getBoundingClientRect();
              return {{
                x: rect.left + rect.width/2 + Math.random() * rect.width/4,
                y: rect.top + rect.height/2 + Math.random() * rect.height/4
              }};
            }}
            return null;
          """)

          if element_bounds:
            mouse_x = element_bounds.get('x', random.randint(100, 500))
            mouse_y = element_bounds.get('y', random.randint(100, 500))
          else:
            mouse_x = random.randint(100, 500)
            mouse_y = random.randint(100, 500)
        else:
          mouse_x = random.randint(100, 500)
          mouse_y = random.randint(100, 500)

        await self.current_tab.send(cdp.input_.dispatch_mouse_event(
          type_="mouseWheel",
          x=mouse_x,
          y=mouse_y,
          delta_x=scroll_x,
          delta_y=scroll_y
        ))

        current_scroll += abs(scroll_x or scroll_y)

        # Micro-pause between wheel notches (acceleration curve)
        # Faster in middle of burst, slower at ends
        if burst_step == 0 or burst_step == burst_length - 1:
          await asyncio.sleep(random.uniform(0.03, 0.06))  # Slower at ends
        else:
          await asyncio.sleep(random.uniform(0.01, 0.03))  # Faster in middle

      scroll_count += 1

      # 2. "Reading Pause" between bursts
      # 35% chance to stop and "read" (increased for more human-like behavior)
      if random.random() < 0.35:
        await asyncio.sleep(random.uniform(0.8, 2.0))  # Reading pause
      else:
        # Standard pause between flicks
        await asyncio.sleep(random.uniform(0.15, 0.4))

      # Check if we've scrolled enough or hit a limit
      if current_scroll >= distance:
        break

    target_desc = f"element '{element_selector}'" if element_selector else "page"
    return f"Scrolled {direction} on {target_desc}: {current_scroll}px in {scroll_count} bursts"

  async def start_network_interception(self) -> None:
    """Start intercepting network requests."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    if self.intercepting:
      return

    logger.info("Starting network interception")
    await self.current_tab.send(cdp.network.enable())
    self.network_events = []

    # Add network event handlers
    self.current_tab.add_handler(cdp.network.RequestWillBeSent, self._on_request)
    self.current_tab.add_handler(cdp.network.ResponseReceived, self._on_response)
    self.intercepting = True

  async def stop_network_interception(self) -> None:
    """Stop intercepting network requests."""
    if not self.current_tab:
      return

    if not self.intercepting:
      return

    logger.info("Stopping network interception")
    await self.current_tab.send(cdp.network.disable())
    self.intercepting = False

  async def start_websocket_interception(self) -> None:
    """Start intercepting WebSocket connections and frames."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    if self.ws_intercepting:
      return

    logger.info("Starting WebSocket interception")
    # Network must be enabled for WebSocket events
    await self.current_tab.send(cdp.network.enable())
    self.websocket_frames = []
    self.websocket_connections = {}

    # Add WebSocket event handlers
    self.current_tab.add_handler(cdp.network.WebSocketCreated, self._on_ws_created)
    self.current_tab.add_handler(cdp.network.WebSocketFrameReceived, self._on_ws_frame_received)
    self.current_tab.add_handler(cdp.network.WebSocketFrameSent, self._on_ws_frame_sent)
    self.current_tab.add_handler(cdp.network.WebSocketClosed, self._on_ws_closed)
    self.ws_intercepting = True

  async def stop_websocket_interception(self) -> None:
    """Stop intercepting WebSocket connections."""
    if not self.current_tab:
      return

    if not self.ws_intercepting:
      return

    logger.info("Stopping WebSocket interception")
    try:
      self.current_tab.remove_handler(cdp.network.WebSocketCreated, self._on_ws_created)
      self.current_tab.remove_handler(cdp.network.WebSocketFrameReceived, self._on_ws_frame_received)
      self.current_tab.remove_handler(cdp.network.WebSocketFrameSent, self._on_ws_frame_sent)
      self.current_tab.remove_handler(cdp.network.WebSocketClosed, self._on_ws_closed)
    except Exception:
      pass
    self.ws_intercepting = False

  def _on_ws_created(self, event: cdp.network.WebSocketCreated, tab=None) -> None:
    """Handle WebSocket connection creation."""
    request_id = str(event.request_id)
    self.websocket_connections[request_id] = {
      "url": event.url,
      "created_at": datetime.now().isoformat(),
      "initiator": str(event.initiator) if event.initiator else None
    }
    logger.info(f"WebSocket created: {event.url}")

  def _on_ws_frame_received(self, event: cdp.network.WebSocketFrameReceived, tab=None) -> None:
    """Handle incoming WebSocket frames."""
    frame_data = {
      "type": "received",
      "timestamp": datetime.now().isoformat(),
      "request_id": str(event.request_id),
      "opcode": event.response.opcode,
      "payload_data": event.response.payload_data,
      "mask": event.response.mask if hasattr(event.response, 'mask') else None
    }

    # Ring buffer to prevent memory explosion
    if len(self.websocket_frames) > 5000:
      self.websocket_frames.pop(0)

    self.websocket_frames.append(frame_data)
    logger.debug(f"WS frame received: {len(event.response.payload_data)} bytes")

  def _on_ws_frame_sent(self, event: cdp.network.WebSocketFrameSent, tab=None) -> None:
    """Handle outgoing WebSocket frames."""
    frame_data = {
      "type": "sent",
      "timestamp": datetime.now().isoformat(),
      "request_id": str(event.request_id),
      "opcode": event.response.opcode,
      "payload_data": event.response.payload_data,
      "mask": event.response.mask if hasattr(event.response, 'mask') else None
    }

    # Ring buffer to prevent memory explosion
    if len(self.websocket_frames) > 5000:
      self.websocket_frames.pop(0)

    self.websocket_frames.append(frame_data)
    logger.debug(f"WS frame sent: {len(event.response.payload_data)} bytes")

  def _on_ws_closed(self, event: cdp.network.WebSocketClosed, tab=None) -> None:
    """Handle WebSocket connection close."""
    request_id = str(event.request_id)
    if request_id in self.websocket_connections:
      self.websocket_connections[request_id]["closed_at"] = datetime.now().isoformat()
    logger.info(f"WebSocket closed: {request_id}")

  def get_websocket_frames(self, filter_pattern: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get captured WebSocket frames, optionally filtered by payload pattern."""
    import re
    frames = self.websocket_frames
    if filter_pattern:
      frames = [f for f in frames if re.search(filter_pattern, f.get("payload_data", ""), re.IGNORECASE)]
    return frames

  def get_websocket_connections(self) -> Dict[str, Dict[str, Any]]:
    """Get all WebSocket connections."""
    return self.websocket_connections

  def clear_websocket_frames(self) -> None:
    """Clear all captured WebSocket frames."""
    self.websocket_frames = []

  def _on_request(self, event: cdp.network.RequestWillBeSent, tab=None) -> None:
    """Handle network request events."""
    # FILTER: Ignore static assets to save memory/tokens
    if hasattr(event, 'type_') and event.type_ in ["Image", "Stylesheet", "Font", "Media", "Script"]:
      return

    event_data = {
        "type": "request",
        "timestamp": datetime.now().isoformat(),
        "request_id": event.request_id,
        "url": event.request.url,
        "method": event.request.method,
        # Only keep headers if it's an API call to save space
        "headers": dict(event.request.headers) if event.request.headers and ("json" in str(event.request.headers).lower() or "api" in event.request.url.lower()) else {},
        "post_data": event.request.post_data if hasattr(event.request, 'post_data') else None,
    }

    # Ring buffer: prevent memory explosion
    if len(self.network_events) > 1000:
      self.network_events.pop(0)

    self.network_events.append(event_data)
    logger.debug(f"Request: {event.request.url}")

  def _on_response(self, event: cdp.network.ResponseReceived, tab=None) -> None:
    """Handle network response events."""
    # FILTER: Ignore static assets
    if hasattr(event.response, 'mime_type') and event.response.mime_type in [
      "text/css", "image/", "font/", "application/font", "audio/", "video/"
    ]:
      return

    event_data = {
        "type": "response",
        "timestamp": datetime.now().isoformat(),
        "request_id": event.request_id,
        "url": event.response.url,
        "status": event.response.status,
        "status_text": event.response.status_text,
        "headers": dict(event.response.headers) if event.response.headers else {},
        "mime_type": event.response.mime_type,
    }

    # Ring buffer: prevent memory explosion
    if len(self.network_events) > 1000:
      self.network_events.pop(0)

    self.network_events.append(event_data)
    logger.debug(f"Response: {event.response.url} ({event.response.status})")

  def get_network_events(self, filter_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get captured network events, optionally filtered by URL pattern."""
    events = self.network_events
    if filter_url:
      events = [e for e in events if filter_url.lower() in e.get("url", "").lower()]
    return events

  async def refresh_page(self) -> None:
    """Refresh the current page."""
    if not self.current_tab:
      raise RuntimeError("No active tab")

    logger.info("Refreshing current page")
    await self.current_tab.reload()
    logger.info("Page refresh completed")

  def save_network_responses(self, filter_pattern: Optional[str] = None, output_dir: str = "network_responses") -> List[str]:
    """Save captured network responses to JSON files.

    Args:
        filter_pattern: Optional regex pattern to filter URLs
        output_dir: Directory to save responses (relative to server.py location)

    Returns:
        List of saved file paths
    """
    import json
    import os
    import re
    from datetime import datetime

    # Create output directory
    output_path = os.path.join(os.path.dirname(__file__), output_dir)
    os.makedirs(output_path, exist_ok=True)

    saved_files = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for i, event in enumerate(self.network_events):
      url = event.get('url', '')
      if not url:
        continue

      # Apply filter if provided
      if filter_pattern and not re.search(filter_pattern, url, re.IGNORECASE):
        continue

      # Create filename from URL
      url_parts = url.replace('https://', '').replace('http://', '').split('/')
      domain = url_parts[0].replace('.', '_')
      endpoint = '_'.join(url_parts[1:3]) if len(url_parts) > 1 else 'unknown'

      filename = f"{timestamp}_{i:03d}_{domain}_{endpoint}.json"
      filepath = os.path.join(output_path, filename)

      # Save the full event data
      with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(event, f, indent=2, ensure_ascii=False)

      saved_files.append(filepath)
      logger.info(f"Saved network response: {filename}")

    logger.info(f"Saved {len(saved_files)} network responses to {output_path}")
    return saved_files

  def analyze_network_responses(self, analysis_code: str) -> Any:
    """Run custom Python analysis code on captured network responses.

    Args:
        analysis_code: Python code string to execute with 'responses' variable available

    Returns:
        Result of the analysis code execution
    """
    import json

    # Make responses available to the analysis code
    responses = self.network_events

    try:
      # Create a safe execution environment
      local_vars = {
        'responses': responses,
        'json': json,
        'len': len,
        'print': print,
        'str': str,
        'int': int,
        'float': float,
        'list': list,
        'dict': dict,
        'set': set,
      }

      # Execute the analysis code
      result = eval(analysis_code, {"__builtins__": {}}, local_vars)
      logger.info("Analysis code executed successfully")
      return result

    except Exception as e:
      logger.error(f"Analysis code execution failed: {e}")
      raise

  def get_network_summary(self, filter_pattern: Optional[str] = None) -> Dict[str, Any]:
    """Get a summary of captured network activity.

    Args:
        filter_pattern: Optional regex pattern to filter URLs

    Returns:
        Dictionary with network statistics
    """
    import re

    events = self.network_events
    if filter_pattern:
      events = [e for e in events if re.search(filter_pattern, e.get('url', ''), re.IGNORECASE)]

    unique_urls = set()
    methods = {}
    domains = {}

    for event in events:
      url = event.get('url', '')
      method = event.get('method', 'UNKNOWN')

      if url:
        unique_urls.add(url.split('?')[0])  # Base URL without params

        # Count methods
        methods[method] = methods.get(method, 0) + 1

        # Count domains
        try:
          domain = url.split('://')[1].split('/')[0]
          domains[domain] = domains.get(domain, 0) + 1
        except:
          pass

    return {
      'total_requests': len(events),
      'unique_endpoints': len(unique_urls),
      'methods': methods,
      'top_domains': dict(sorted(domains.items(), key=lambda x: x[1], reverse=True)[:10]),
      'sample_urls': list(unique_urls)[:5] if unique_urls else []
    }

  async def press_and_hold(self, x: float, y: float, duration: float = 3.0, release_selector: Optional[str] = None) -> str:
    """Simulate a press-and-hold (mousedown, wait, mouseup) at browser level.
    Uses CDP Input.dispatchMouseEvent which produces trusted events that
    bypass PerimeterX and similar bot detection.

    If release_selector is provided, polls every 500ms and releases early
    when the element disappears from the DOM (e.g., '#px-captcha' removed
    after successful hold). Falls back to max duration if element persists.
    """
    if not self.current_tab:
      raise RuntimeError("No active tab")
    from nodriver.cdp.input_ import dispatch_mouse_event, MouseButton
    # mousePressed
    await self.current_tab.send(dispatch_mouse_event(
      type_="mousePressed", x=x, y=y,
      button=MouseButton.LEFT, click_count=1, pointer_type="mouse"
    ))
    logger.info("press_and_hold: mousePressed at (%.0f, %.0f), max %.1fs, release_selector=%s", x, y, duration, release_selector)

    held_for = 0.0
    poll_interval = 0.5
    released_early = False
    while held_for < duration:
      await asyncio.sleep(poll_interval)
      held_for += poll_interval
      if release_selector:
        try:
          result = await self.current_tab.send(
            cdp.runtime.evaluate(expression=f"!!document.querySelector('{release_selector}')")
          )
          still_present = getattr(getattr(result, 'result', None), 'value', True)
          if not still_present:
            logger.info("press_and_hold: release_selector '%s' gone after %.1fs — releasing early", release_selector, held_for)
            released_early = True
            break
        except Exception:
          pass

    # mouseReleased
    await self.current_tab.send(dispatch_mouse_event(
      type_="mouseReleased", x=x, y=y,
      button=MouseButton.LEFT, click_count=1, pointer_type="mouse"
    ))
    if released_early:
      logger.info("press_and_hold: released early at (%.0f, %.0f) after %.1fs", x, y, held_for)
      return f"Press and hold at ({x}, {y}) — released early after {held_for:.1f}s (element gone)"
    else:
      logger.info("press_and_hold: released at (%.0f, %.0f) after max %.1fs", x, y, duration)
      return f"Press and hold at ({x}, {y}) for {duration}s completed (max duration reached)"

  async def execute_cdp_command(self, command: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Execute a raw Chrome DevTools Protocol command.

    Args:
        command: CDP command name (e.g., 'Page.reload', 'Network.getResponseBody')
        params: Command parameters as dictionary

    Returns:
        CDP command result
    """
    import json

    if not self.current_tab:
      raise RuntimeError("No active tab")

    try:
      # Use nodriver's CDP command execution
      cdp_module = getattr(cdp, command.split('.')[0], None)
      if cdp_module:
        cdp_command = getattr(cdp_module, command.split('.')[1], None)
        if cdp_command and params:
          result = await self.current_tab.send(cdp_command(**params))
        elif cdp_command:
          result = await self.current_tab.send(cdp_command())
        else:
          raise ValueError(f"Unknown CDP command: {command}")
      else:
        raise ValueError(f"Unknown CDP module: {command.split('.')[0]}")

      logger.info(f"Executed CDP command: {command}")
      return result
    except Exception as e:
      logger.error(f"CDP command failed: {command} - {e}")
      raise


# Global browser session
browser_session = BrowserSession()


def create_tool(name: str, description: str, input_schema: Dict[str, Any]) -> Tool:
  """Create a Tool object for the MCP server."""
  return Tool(
    name=name,
    description=description,
    inputSchema=input_schema
  )


async def handle_start_browser(headless: bool = False) -> List[TextContent]:
  """Start the browser session."""
  try:
    await browser_session.start_browser(headless=headless)
    return [TextContent(
      type="text",
      text="Browser started successfully"
    )]
  except Exception as e:
    logger.error(f"Failed to start browser: {e}")
    return [TextContent(
      type="text",
      text=f"Error starting browser: {str(e)}"
    )]


async def handle_stop_browser() -> List[TextContent]:
  """Stop the browser session."""
  try:
    await browser_session.stop_browser()
    return [TextContent(
      type="text",
      text="Browser stopped successfully"
    )]
  except Exception as e:
    logger.error(f"Failed to stop browser: {e}")
    return [TextContent(
      type="text",
      text=f"Error stopping browser: {str(e)}"
    )]


async def handle_navigate(url: str) -> List[TextContent]:
  """Navigate to a URL."""
  try:
    await browser_session.navigate(url)
    return [TextContent(
      type="text",
      text=f"Successfully navigated to {url}"
    )]
  except Exception as e:
    logger.error(f"Failed to navigate to {url}: {e}")
    return [TextContent(
      type="text",
      text=f"Error navigating to {url}: {str(e)}"
    )]


async def handle_click_element(selector: str, timeout: int = 10) -> List[TextContent]:
  """Click an element by CSS selector."""
  try:
    await browser_session.click_element(selector, timeout)
    return [TextContent(
      type="text",
      text=f"Successfully clicked element: {selector}"
    )]
  except Exception as e:
    logger.error(f"Failed to click element {selector}: {e}")
    return [TextContent(
      type="text",
      text=f"Error clicking element {selector}: {str(e)}"
    )]


async def handle_wait_for_element(selector: str, timeout: int = 10) -> List[TextContent]:
  """Wait for an element to appear."""
  try:
    await browser_session.wait_for_element(selector, timeout)
    return [TextContent(
      type="text",
      text=f"Element found: {selector}"
    )]
  except Exception as e:
    logger.error(f"Element not found {selector}: {e}")
    return [TextContent(
      type="text",
      text=f"Error waiting for element {selector}: {str(e)}"
    )]


async def handle_get_page_source() -> List[TextContent]:
  """Get the current page HTML source."""
  try:
    source = await browser_session.get_page_source()
    # Truncate very long HTML for readability
    if len(source) > 50000:
      source = source[:50000] + "\n\n[... HTML truncated for readability ...]"

    return [TextContent(
      type="text",
      text=f"Page source:\n{source}"
    )]
  except Exception as e:
    logger.error(f"Failed to get page source: {e}")
    return [TextContent(
      type="text",
      text=f"Error getting page source: {str(e)}"
    )]


async def handle_execute_javascript(script: str) -> List[TextContent]:
  """Execute JavaScript in the current tab."""
  try:
    result = await browser_session.execute_javascript(script)
    return [TextContent(
      type="text",
      text=f"JavaScript result: {json.dumps(result, indent=2)}"
    )]
  except Exception as e:
    logger.error(f"Failed to execute JavaScript: {e}")
    return [TextContent(
      type="text",
      text=f"Error executing JavaScript: {str(e)}"
    )]


async def handle_take_screenshot() -> list:
  """Take a screenshot of the current page."""
  try:
    screenshot_b64 = await browser_session.take_screenshot()

    return [ImageContent(
      type="image",
      data=screenshot_b64,
      mimeType="image/png"
    )]
  except Exception as e:
    logger.error(f"Failed to take screenshot: {e}")
    return [TextContent(
      type="text",
      text=f"Error taking screenshot: {str(e)}"
    )]


async def handle_start_network_interception() -> List[TextContent]:
  """Start intercepting network requests."""
  try:
    await browser_session.start_network_interception()
    return [TextContent(
      type="text",
      text="Network interception started successfully"
    )]
  except Exception as e:
    logger.error(f"Failed to start network interception: {e}")
    return [TextContent(
      type="text",
      text=f"Error starting network interception: {str(e)}"
    )]


async def handle_stop_network_interception() -> List[TextContent]:
  """Stop intercepting network requests."""
  try:
    await browser_session.stop_network_interception()
    return [TextContent(
      type="text",
      text="Network interception stopped successfully"
    )]
  except Exception as e:
    logger.error(f"Failed to stop network interception: {e}")
    return [TextContent(
      type="text",
      text=f"Error stopping network interception: {str(e)}"
    )]


async def handle_get_network_events(filter_url: Optional[str] = None) -> List[TextContent]:
  """Get captured network events."""
  try:
    events = browser_session.get_network_events(filter_url)
    events_json = json.dumps(events, indent=2)

    # Truncate if too many events
    if len(events) > 50:
      events_json = json.dumps(events[:50], indent=2) + f"\n\n[... showing first 50 of {len(events)} events ...]"

    return [TextContent(
      type="text",
      text=f"Network events ({len(events)} total):\n{events_json}"
    )]
  except Exception as e:
    logger.error(f"Failed to get network events: {e}")
    return [TextContent(
      type="text",
      text=f"Error getting network events: {str(e)}"
    )]


async def handle_clear_network_events() -> List[TextContent]:
    """Clear captured network events."""
    try:
        browser_session.network_events = []
        return [TextContent(
            type="text",
            text="Network events cleared successfully"
        )]
    except Exception as e:
        logger.error(f"Failed to clear network events: {e}")
        return [TextContent(
            type="text",
            text=f"Error clearing network events: {str(e)}"
        )]


async def handle_get_accessibility_tree() -> List[TextContent]:
    """Get a simplified text representation of the page structure."""
    try:
        tree = await browser_session.get_accessibility_tree()
        return [TextContent(
            type="text",
            text=f"Accessibility Tree:\n{tree}"
        )]
    except Exception as e:
        logger.error(f"Failed to get accessibility tree: {e}")
        return [TextContent(
            type="text",
            text=f"Error getting accessibility tree: {str(e)}"
        )]


async def handle_save_cookies(filepath: str = "cookies.json") -> List[TextContent]:
    """Save current browser cookies to a file."""
    try:
        await browser_session.save_cookies(filepath)
        return [TextContent(
            type="text",
            text=f"Cookies saved to {filepath}"
        )]
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")
        return [TextContent(
            type="text",
            text=f"Error saving cookies: {str(e)}"
        )]


async def handle_load_cookies(filepath: str = "cookies.json") -> List[TextContent]:
    """Load cookies from a file into the browser."""
    try:
        await browser_session.load_cookies(filepath)
        return [TextContent(
            type="text",
            text=f"Cookies loaded from {filepath}"
        )]
    except Exception as e:
        logger.error(f"Failed to load cookies: {e}")
        return [TextContent(
            type="text",
            text=f"Error loading cookies: {str(e)}"
        )]


async def handle_wait_for_network_idle(timeout: int = 10, idle_time: int = 2) -> List[TextContent]:
    """Wait for network activity to become idle."""
    try:
        await browser_session.wait_for_network_idle(timeout, idle_time)
        return [TextContent(
            type="text",
            text=f"Network idle detected (waited up to {timeout}s for {idle_time}s of inactivity)"
        )]
    except Exception as e:
        logger.error(f"Failed to wait for network idle: {e}")
        return [TextContent(
            type="text",
            text=f"Error waiting for network idle: {str(e)}"
        )]


async def handle_type_text(selector: str, text: str, delay_range: Optional[List[int]] = None) -> List[TextContent]:
    """Type text into an element with human-like delays."""
    try:
        if delay_range is None:
            delay_range = [50, 200]
        await browser_session.type_text(selector, text, delay_range)
        return [TextContent(
            type="text",
            text=f"Successfully typed '{text}' into element: {selector}"
        )]
    except Exception as e:
        logger.error(f"Failed to type text: {e}")
        return [TextContent(
            type="text",
            text=f"Error typing text: {str(e)}"
        )]


async def handle_select_option(selector: str, value: str) -> List[TextContent]:
    """Select an option from a dropdown."""
    try:
        await browser_session.select_option(selector, value)
        return [TextContent(
            type="text",
            text=f"Successfully selected option '{value}' from dropdown: {selector}"
        )]
    except Exception as e:
        logger.error(f"Failed to select option: {e}")
        return [TextContent(
            type="text",
            text=f"Error selecting option: {str(e)}"
        )]


async def handle_switch_to_frame(frame_selector: str) -> List[TextContent]:
    """Switch context to an iframe."""
    try:
        await browser_session.switch_to_frame(frame_selector)
        return [TextContent(
            type="text",
            text=f"Successfully switched to frame: {frame_selector}"
        )]
    except Exception as e:
        logger.error(f"Failed to switch to frame: {e}")
        return [TextContent(
            type="text",
            text=f"Error switching to frame: {str(e)}"
        )]


async def handle_execute_in_frame(frame_selector: str, script: str) -> List[TextContent]:
    """Execute JavaScript inside a specific iframe."""
    try:
        result = await browser_session.execute_in_frame(frame_selector, script)
        return [TextContent(
            type="text",
            text=f"Frame execution result: {json.dumps(result, indent=2)}"
        )]
    except Exception as e:
        logger.error(f"Failed to execute in frame: {e}")
        return [TextContent(
            type="text",
            text=f"Error executing in frame: {str(e)}"
        )]


async def handle_set_device_mode(mobile: bool = True) -> List[TextContent]:
    """Emulate mobile or desktop device."""
    try:
        await browser_session.set_device_mode(mobile)
        return [TextContent(
            type="text",
            text=f"Successfully set device mode: {'mobile' if mobile else 'desktop'}"
        )]
    except Exception as e:
        logger.error(f"Failed to set device mode: {e}")
        return [TextContent(
            type="text",
            text=f"Error setting device mode: {str(e)}"
        )]


async def handle_read_console_logs(level: str = "error") -> List[TextContent]:
    """Read browser console logs."""
    try:
        logs = await browser_session.read_console_logs(level)
        logs_text = json.dumps(logs, indent=2) if logs else "No console logs found"
        return [TextContent(
            type="text",
            text=f"Console logs ({level} level):\n{logs_text}"
        )]
    except Exception as e:
        logger.error(f"Failed to read console logs: {e}")
        return [TextContent(
            type="text",
            text=f"Error reading console logs: {str(e)}"
        )]


async def handle_get_cleaned_html() -> List[TextContent]:
    """Get HTML with scripts, styles, and images removed."""
    try:
        html = await browser_session.get_cleaned_html()
        # Truncate if too long
        if len(html) > 30000:
            html = html[:30000] + "\n\n[... HTML truncated for readability ...]"
        return [TextContent(
            type="text",
            text=f"Cleaned HTML:\n{html}"
        )]
    except Exception as e:
        logger.error(f"Failed to get cleaned HTML: {e}")
        return [TextContent(
            type="text",
            text=f"Error getting cleaned HTML: {str(e)}"
        )]


async def handle_verify_curl(url: str, headers: Optional[Dict[str, str]] = None) -> List[TextContent]:
    """Verify if a captured request works."""
    try:
        if headers is None:
            headers = {}
        result = await browser_session.verify_curl(url, headers)
        return [TextContent(
            type="text",
            text=f"CURL verification result:\n{json.dumps(result, indent=2)}"
        )]
    except Exception as e:
        logger.error(f"Failed to verify CURL: {e}")
        return [TextContent(
            type="text",
            text=f"Error verifying CURL: {str(e)}"
        )]


async def handle_human_click(selector: str, hover: bool = True, hover_delay: Optional[List[float]] = None) -> List[TextContent]:
    """Perform a human-like click with mouse movement."""
    try:
        if hover_delay is None:
            hover_delay = [0.5, 1.5]
        await browser_session.human_click(selector, hover, hover_delay)
        return [TextContent(
            type="text",
            text=f"Successfully performed human click on: {selector}"
        )]
    except Exception as e:
        logger.error(f"Failed to perform human click: {e}")
        return [TextContent(
            type="text",
            text=f"Error performing human click: {str(e)}"
        )]


async def handle_scroll_page(direction: str = "down", distance: Optional[int] = None,
                           max_scrolls: Optional[int] = None, element_selector: Optional[str] = None) -> List[TextContent]:
    """Scroll the page or element in a human-like manner."""
    try:
        result = await browser_session.human_scroll(direction, distance, max_scrolls, element_selector)
        return [TextContent(
            type="text",
            text=result
        )]
    except Exception as e:
        logger.error(f"Failed to scroll: {e}")
        return [TextContent(
            type="text",
            text=f"Error scrolling: {str(e)}"
        )]


async def handle_refresh_page() -> List[TextContent]:
  """Refresh the current page."""
  try:
    await browser_session.refresh_page()
    return [TextContent(
      type="text",
      text="Page refreshed successfully"
    )]
  except Exception as e:
    return [TextContent(
      type="text",
      text=f"Failed to refresh page: {e}"
    )]


async def handle_save_network_responses(filter_pattern: Optional[str] = None, output_dir: str = "network_responses") -> List[TextContent]:
  """Save captured network responses to JSON files."""
  try:
    saved_files = browser_session.save_network_responses(filter_pattern, output_dir)
    return [TextContent(
      type="text",
      text=f"Saved {len(saved_files)} network responses to {output_dir}/:\n" + "\n".join(saved_files)
    )]
  except Exception as e:
    return [TextContent(
      type="text",
      text=f"Failed to save network responses: {e}"
    )]


async def handle_analyze_network_responses(analysis_code: str) -> List[TextContent]:
  """Run custom Python analysis code on captured network responses."""
  try:
    result = browser_session.analyze_network_responses(analysis_code)
    return [TextContent(
      type="text",
      text=f"Analysis result: {result}"
    )]
  except Exception as e:
    return [TextContent(
      type="text",
      text=f"Analysis failed: {e}"
    )]


async def handle_get_network_summary(filter_pattern: Optional[str] = None) -> List[TextContent]:
  """Get a summary of captured network activity."""
  try:
    summary = browser_session.get_network_summary(filter_pattern)
    result = f"""Network Summary:
Total Requests: {summary['total_requests']}
Unique Endpoints: {summary['unique_endpoints']}
HTTP Methods: {summary['methods']}
Top Domains: {summary['top_domains']}
Sample URLs: {summary['sample_urls'][:5]}"""
    return [TextContent(
      type="text",
      text=result
    )]
  except Exception as e:
    return [TextContent(
      type="text",
      text=f"Failed to get network summary: {e}"
    )]


async def handle_press_and_hold(x: float, y: float, duration: float = 15.0, release_selector: Optional[str] = None) -> List[TextContent]:
  """Press and hold at coordinates for a duration (solves PerimeterX captchas)."""
  try:
    result = await browser_session.press_and_hold(x, y, duration, release_selector)
    return [TextContent(type="text", text=result)]
  except Exception as e:
    logger.error(f"Press and hold failed: {e}")
    return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_execute_cdp_command(command: str, params: Optional[Dict[str, Any]] = None) -> List[TextContent]:
  """Execute a raw Chrome DevTools Protocol command."""
  try:
    result = await browser_session.execute_cdp_command(command, params)
    return [TextContent(
      type="text",
      text=f"CDP Command Result: {result}"
    )]
  except Exception as e:
    return [TextContent(
      type="text",
      text=f"CDP command failed: {e}"
    )]


async def handle_start_websocket_interception() -> List[TextContent]:
  """Start intercepting WebSocket connections and frames."""
  try:
    await browser_session.start_websocket_interception()
    return [TextContent(
      type="text",
      text="WebSocket interception started successfully"
    )]
  except Exception as e:
    logger.error(f"Failed to start WebSocket interception: {e}")
    return [TextContent(
      type="text",
      text=f"Error starting WebSocket interception: {str(e)}"
    )]


async def handle_stop_websocket_interception() -> List[TextContent]:
  """Stop intercepting WebSocket connections."""
  try:
    await browser_session.stop_websocket_interception()
    return [TextContent(
      type="text",
      text="WebSocket interception stopped successfully"
    )]
  except Exception as e:
    logger.error(f"Failed to stop WebSocket interception: {e}")
    return [TextContent(
      type="text",
      text=f"Error stopping WebSocket interception: {str(e)}"
    )]


async def handle_get_websocket_frames(filter_pattern: Optional[str] = None) -> List[TextContent]:
  """Get captured WebSocket frames."""
  try:
    frames = browser_session.get_websocket_frames(filter_pattern)

    # Truncate if too many frames
    if len(frames) > 100:
      frames_json = json.dumps(frames[:100], indent=2) + f"\n\n[... showing first 100 of {len(frames)} frames ...]"
    else:
      frames_json = json.dumps(frames, indent=2)

    return [TextContent(
      type="text",
      text=f"WebSocket frames ({len(frames)} total):\n{frames_json}"
    )]
  except Exception as e:
    logger.error(f"Failed to get WebSocket frames: {e}")
    return [TextContent(
      type="text",
      text=f"Error getting WebSocket frames: {str(e)}"
    )]


async def handle_get_websocket_connections() -> List[TextContent]:
  """Get all WebSocket connections."""
  try:
    connections = browser_session.get_websocket_connections()
    return [TextContent(
      type="text",
      text=f"WebSocket connections ({len(connections)} total):\n{json.dumps(connections, indent=2)}"
    )]
  except Exception as e:
    logger.error(f"Failed to get WebSocket connections: {e}")
    return [TextContent(
      type="text",
      text=f"Error getting WebSocket connections: {str(e)}"
    )]


async def handle_clear_websocket_frames() -> List[TextContent]:
  """Clear all captured WebSocket frames."""
  try:
    browser_session.clear_websocket_frames()
    return [TextContent(
      type="text",
      text="WebSocket frames cleared successfully"
    )]
  except Exception as e:
    logger.error(f"Failed to clear WebSocket frames: {e}")
    return [TextContent(
      type="text",
      text=f"Error clearing WebSocket frames: {str(e)}"
    )]


async def main():
  """Main MCP server entry point."""
  # Configure logging
  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  )

  server = Server("nodriver-mcp-server")

  @server.list_tools()
  async def handle_list_tools() -> List[Tool]:
    """List all available tools."""
    return [
      create_tool(
        name="start_browser",
        description="Start a new browser session with nodriver",
        input_schema={
          "type": "object",
          "properties": {
	                        "headless": {
	                            "type": "boolean",
	                            "description": "Run browser in headless mode. Use false for logged-in application and LinkedIn workflows.",
	                            "default": False
	                        }
          }
        }
      ),
      create_tool(
        name="stop_browser",
        description="Stop the current browser session",
        input_schema={
          "type": "object",
          "properties": {}
        }
      ),
      create_tool(
        name="navigate",
        description="Navigate to a URL",
        input_schema={
          "type": "object",
          "properties": {
            "url": {
              "type": "string",
              "description": "The URL to navigate to"
            }
          },
          "required": ["url"]
        }
      ),
      create_tool(
        name="click_element",
        description="Click an element by CSS selector",
        input_schema={
          "type": "object",
          "properties": {
            "selector": {
              "type": "string",
              "description": "CSS selector for the element to click"
            },
            "timeout": {
              "type": "integer",
              "description": "Timeout in seconds to wait for element (default: 10)",
              "default": 10
            }
          },
          "required": ["selector"]
        }
      ),
      create_tool(
        name="wait_for_element",
        description="Wait for an element to appear by CSS selector",
        input_schema={
          "type": "object",
          "properties": {
            "selector": {
              "type": "string",
              "description": "CSS selector for the element to wait for"
            },
            "timeout": {
              "type": "integer",
              "description": "Timeout in seconds (default: 10)",
              "default": 10
            }
          },
          "required": ["selector"]
        }
      ),
      create_tool(
        name="get_page_source",
        description="Get the current page HTML source",
        input_schema={
          "type": "object",
          "properties": {}
        }
      ),
      create_tool(
        name="execute_javascript",
        description="Execute JavaScript code in the current page",
        input_schema={
          "type": "object",
          "properties": {
            "script": {
              "type": "string",
              "description": "JavaScript code to execute"
            }
          },
          "required": ["script"]
        }
      ),
      create_tool(
        name="take_screenshot",
        description="Take a screenshot of the current page",
        input_schema={
          "type": "object",
          "properties": {}
        }
      ),
      create_tool(
        name="start_network_interception",
        description="Start intercepting network requests and responses",
        input_schema={
          "type": "object",
          "properties": {}
        }
      ),
      create_tool(
        name="stop_network_interception",
        description="Stop intercepting network requests and responses",
        input_schema={
          "type": "object",
          "properties": {}
        }
      ),
      create_tool(
        name="get_network_events",
        description="Get captured network events (requests/responses)",
        input_schema={
          "type": "object",
          "properties": {
            "filter_url": {
              "type": "string",
              "description": "Filter events by URL pattern (optional)"
            }
          }
        }
      ),
            create_tool(
                name="clear_network_events",
                description="Clear all captured network events",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            create_tool(
                name="get_accessibility_tree",
                description="Get a simplified text representation of page elements for AI analysis",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            create_tool(
                name="save_cookies",
                description="Save current browser cookies to a JSON file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "Path to save cookies (default: cookies.json)",
                            "default": "cookies.json"
                        }
                    }
                }
            ),
            create_tool(
                name="load_cookies",
                description="Load cookies from a JSON file into the browser",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "Path to load cookies from (default: cookies.json)",
                            "default": "cookies.json"
                        }
                    }
                }
            ),
            create_tool(
                name="wait_for_network_idle",
                description="Wait for network activity to become idle (no requests for specified time)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "timeout": {
                            "type": "integer",
                            "description": "Maximum time to wait in seconds (default: 10)",
                            "default": 10
                        },
                        "idle_time": {
                            "type": "integer",
                            "description": "Time with no network activity required (default: 2)",
                            "default": 2
                        }
                    }
                }
            ),
            create_tool(
                name="type_text",
                description="Type text into an element with human-like delays between keystrokes",
                input_schema={
                    "type": "object",
                    "properties": {
                        "selector": {
                            "type": "string",
                            "description": "CSS selector for the input element"
                        },
                        "text": {
                            "type": "string",
                            "description": "Text to type"
                        },
                        "delay_range": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Min/max delay in ms between keystrokes (default: [50, 200])",
                            "default": [50, 200]
                        }
                    },
                    "required": ["selector", "text"]
                }
            ),
            create_tool(
                name="select_option",
                description="Select an option from a dropdown and fire change event",
                input_schema={
                    "type": "object",
                    "properties": {
                        "selector": {
                            "type": "string",
                            "description": "CSS selector for the dropdown"
                        },
                        "value": {
                            "type": "string",
                            "description": "Value to select"
                        }
                    },
                    "required": ["selector", "value"]
                }
            ),
            create_tool(
                name="switch_to_frame",
                description="Switch context to an iframe",
                input_schema={
                    "type": "object",
                    "properties": {
                        "frame_selector": {
                            "type": "string",
                            "description": "CSS selector for the iframe element"
                        }
                    },
                    "required": ["frame_selector"]
                }
            ),
            create_tool(
                name="execute_in_frame",
                description="Execute JavaScript inside a specific iframe",
                input_schema={
                    "type": "object",
                    "properties": {
                        "frame_selector": {
                            "type": "string",
                            "description": "CSS selector for the iframe element"
                        },
                        "script": {
                            "type": "string",
                            "description": "JavaScript code to execute"
                        }
                    },
                    "required": ["frame_selector", "script"]
                }
            ),
            create_tool(
                name="set_device_mode",
                description="Emulate mobile or desktop device",
                input_schema={
                    "type": "object",
                    "properties": {
                        "mobile": {
                            "type": "boolean",
                            "description": "Enable mobile mode (default: true)",
                            "default": True
                        }
                    }
                }
            ),
            create_tool(
                name="read_console_logs",
                description="Read browser console logs",
                input_schema={
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "string",
                            "description": "Log level to filter by (default: error)",
                            "default": "error",
                            "enum": ["error", "warning", "info", "log"]
                        }
                    }
                }
            ),
            create_tool(
                name="get_cleaned_html",
                description="Get HTML with scripts, styles, and images removed for token savings",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            create_tool(
                name="verify_curl",
                description="Verify if a captured request works by testing in browser context",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to test"
                        },
                        "headers": {
                            "type": "object",
                            "description": "Headers to include in request"
                        }
                    },
                    "required": ["url"]
                }
            ),
            create_tool(
                name="human_click",
                description="Perform a human-like click by moving mouse to random position within element",
                input_schema={
                    "type": "object",
                    "properties": {
                        "selector": {
                            "type": "string",
                            "description": "CSS selector for the element to click"
                        },
                        "hover": {
                            "type": "boolean",
                            "description": "Simulate hover before clicking (default: true)",
                            "default": True
                        },
                        "hover_delay": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Min/max hover delay in seconds (default: [0.5, 1.5])",
                            "default": [0.5, 1.5]
                        }
                    },
                    "required": ["selector"]
                }
            ),
            create_tool(
                name="scroll_page",
                description="Scroll the page or element in a human-like manner with pauses and variable speeds",
                input_schema={
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "description": "Direction to scroll: 'up', 'down', 'left', 'right'",
                            "enum": ["up", "down", "left", "right"],
                            "default": "down"
                        },
                        "distance": {
                            "type": "integer",
                            "description": "Approximate pixels to scroll (default: random 800-1500)",
                            "minimum": 100,
                            "maximum": 10000
                        },
                        "max_scrolls": {
                            "type": "integer",
                            "description": "Maximum number of scroll bursts (default: 50)",
                            "minimum": 1,
                            "maximum": 100,
                            "default": 50
                        },
                        "element_selector": {
                            "type": "string",
                            "description": "CSS selector of element to scroll within (optional, scrolls page if not provided)"
                        }
                    }
                }
            ),
            create_tool(
                name="refresh_page",
                description="Refresh the current page",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            create_tool(
                name="save_network_responses",
                description="Save captured network responses to JSON files in the network_responses directory",
                input_schema={
                    "type": "object",
                    "properties": {
	                        "filter_pattern": {"type": ["string", "null"], "description": "Regex pattern to filter URLs (e.g., 'linkedin', 'greenhouse', 'api')"},
                        "output_dir": {"type": "string", "default": "network_responses", "description": "Directory to save responses"}
                    }
                }
            ),
            create_tool(
                name="analyze_network_responses",
                description="Run custom Python analysis code on captured network responses",
                input_schema={
                    "type": "object",
                    "properties": {
                        "analysis_code": {"type": "string", "description": "Python code to execute (has access to 'responses' variable)"}
                    },
                    "required": ["analysis_code"]
                }
            ),
            create_tool(
                name="get_network_summary",
                description="Get a summary of captured network activity with statistics",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filter_pattern": {"type": ["string", "null"], "description": "Regex pattern to filter URLs"}
                    }
                }
            ),
            create_tool(
                name="execute_cdp_command",
                description="Execute raw Chrome DevTools Protocol commands (advanced)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "CDP command name (e.g., 'Page.reload', 'Network.getResponseBody')"},
                        "params": {"type": ["object", "null"], "description": "Command parameters as JSON object"}
                    },
                    "required": ["command"]
                }
            ),
            create_tool(
                name="press_and_hold",
                description="Press and hold at x,y coordinates for a duration. Uses CDP Input.dispatchMouseEvent for trusted events that bypass PerimeterX captchas. If release_selector is set, releases early when that element disappears from the DOM.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "X coordinate"},
                        "y": {"type": "number", "description": "Y coordinate"},
                        "duration": {"type": "number", "description": "Max hold duration in seconds (default 15.0)", "default": 15.0},
                        "release_selector": {"type": "string", "description": "CSS selector to watch — releases mouse when element disappears (e.g. '#px-captcha')"}
                    },
                    "required": ["x", "y"]
                }
            ),
            # WebSocket interception tools
            create_tool(
                name="start_websocket_interception",
	                description="Start intercepting WebSocket connections and frames for dynamic web apps",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            create_tool(
                name="stop_websocket_interception",
                description="Stop intercepting WebSocket connections",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            create_tool(
                name="get_websocket_frames",
                description="Get captured WebSocket frames (messages sent/received)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filter_pattern": {
                            "type": "string",
                            "description": "Regex pattern to filter frames by payload content (optional)"
                        }
                    }
                }
            ),
            create_tool(
                name="get_websocket_connections",
                description="Get all WebSocket connections that have been established",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            create_tool(
                name="clear_websocket_frames",
                description="Clear all captured WebSocket frames",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
        ]

  @server.call_tool()
  async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    if name == "start_browser":
      headless = arguments.get("headless", False)
      return await handle_start_browser(headless)
    elif name == "stop_browser":
      return await handle_stop_browser()
    elif name == "navigate":
      url = arguments["url"]
      return await handle_navigate(url)
    elif name == "click_element":
      selector = arguments["selector"]
      timeout = arguments.get("timeout", 10)
      return await handle_click_element(selector, timeout)
    elif name == "wait_for_element":
      selector = arguments["selector"]
      timeout = arguments.get("timeout", 10)
      return await handle_wait_for_element(selector, timeout)
    elif name == "get_page_source":
      return await handle_get_page_source()
    elif name == "execute_javascript":
      script = arguments["script"]
      return await handle_execute_javascript(script)
    elif name == "take_screenshot":
      return await handle_take_screenshot()
    elif name == "start_network_interception":
      return await handle_start_network_interception()
    elif name == "stop_network_interception":
      return await handle_stop_network_interception()
    elif name == "get_network_events":
      filter_url = arguments.get("filter_url")
      return await handle_get_network_events(filter_url)
    elif name == "clear_network_events":
      return await handle_clear_network_events()
    elif name == "get_accessibility_tree":
      return await handle_get_accessibility_tree()
    elif name == "save_cookies":
      filepath = arguments.get("filepath", "cookies.json")
      return await handle_save_cookies(filepath)
    elif name == "load_cookies":
      filepath = arguments.get("filepath", "cookies.json")
      return await handle_load_cookies(filepath)
    elif name == "wait_for_network_idle":
      timeout = arguments.get("timeout", 10)
      idle_time = arguments.get("idle_time", 2)
      return await handle_wait_for_network_idle(timeout, idle_time)
    elif name == "type_text":
      selector = arguments["selector"]
      text = arguments["text"]
      delay_range = arguments.get("delay_range", [50, 200])
      return await handle_type_text(selector, text, delay_range)
    elif name == "select_option":
      selector = arguments["selector"]
      value = arguments["value"]
      return await handle_select_option(selector, value)
    elif name == "switch_to_frame":
      frame_selector = arguments["frame_selector"]
      return await handle_switch_to_frame(frame_selector)
    elif name == "execute_in_frame":
      frame_selector = arguments["frame_selector"]
      script = arguments["script"]
      return await handle_execute_in_frame(frame_selector, script)
    elif name == "set_device_mode":
      mobile = arguments.get("mobile", True)
      return await handle_set_device_mode(mobile)
    elif name == "read_console_logs":
      level = arguments.get("level", "error")
      return await handle_read_console_logs(level)
    elif name == "get_cleaned_html":
      return await handle_get_cleaned_html()
    elif name == "verify_curl":
      url = arguments["url"]
      headers = arguments.get("headers", {})
      return await handle_verify_curl(url, headers)
    elif name == "human_click":
      selector = arguments["selector"]
      hover = arguments.get("hover", True)
      hover_delay = arguments.get("hover_delay", [0.5, 1.5])
      return await handle_human_click(selector, hover, hover_delay)
    elif name == "scroll_page":
      direction = arguments.get("direction", "down")
      distance = arguments.get("distance")
      max_scrolls = arguments.get("max_scrolls")
      element_selector = arguments.get("element_selector")
      return await handle_scroll_page(direction, distance, max_scrolls, element_selector)
    elif name == "refresh_page":
      return await handle_refresh_page()
    elif name == "save_network_responses":
      filter_pattern = arguments.get("filter_pattern")
      output_dir = arguments.get("output_dir", "network_responses")
      return await handle_save_network_responses(filter_pattern, output_dir)
    elif name == "analyze_network_responses":
      analysis_code = arguments["analysis_code"]
      return await handle_analyze_network_responses(analysis_code)
    elif name == "get_network_summary":
      filter_pattern = arguments.get("filter_pattern")
      return await handle_get_network_summary(filter_pattern)
    elif name == "execute_cdp_command":
      command = arguments["command"]
      params = arguments.get("params")
      return await handle_execute_cdp_command(command, params)
    elif name == "press_and_hold":
      x = float(arguments["x"])
      y = float(arguments["y"])
      duration = float(arguments.get("duration", 15.0))
      release_selector = arguments.get("release_selector")
      return await handle_press_and_hold(x, y, duration, release_selector)
    # WebSocket interception handlers
    elif name == "start_websocket_interception":
      return await handle_start_websocket_interception()
    elif name == "stop_websocket_interception":
      return await handle_stop_websocket_interception()
    elif name == "get_websocket_frames":
      filter_pattern = arguments.get("filter_pattern")
      return await handle_get_websocket_frames(filter_pattern)
    elif name == "get_websocket_connections":
      return await handle_get_websocket_connections()
    elif name == "clear_websocket_frames":
      return await handle_clear_websocket_frames()
    else:
      return [TextContent(
        type="text",
        text=f"Unknown tool: {name}"
      )]

  # Start the MCP server
  async with stdio_server() as (read_stream, write_stream):
    await server.run(
      read_stream,
      write_stream,
      server.create_initialization_options()
    )


async def test_browser_start():
    """Test function to start browser directly (for development testing only)."""
    print("=== DIRECT BROWSER TEST (DEVELOPMENT ONLY) ===")
    print("This bypasses MCP protocol for testing purposes")

    try:
        result = await handle_start_browser(headless=False)
        print("Browser start result:", result[0].text)

        if "successfully" in result[0].text.lower():
            print("✅ Browser should be visible!")
            print("Press Ctrl+C to stop...")

            # Keep browser running for manual testing
            while True:
                await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping browser...")
        await handle_stop_browser()
        print("Browser stopped")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test-browser":
        # Direct browser test mode
        asyncio.run(test_browser_start())
    else:
        # Normal MCP server mode
        asyncio.run(main())
