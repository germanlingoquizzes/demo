import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from typing import Dict, Optional
import json
import time
from logger import Logger  # Assuming you have a custom logger

class AdsPowerManager:
    def __init__(self, api_key: str, logger: Logger):
        """
        Initialize the AdsPowerManager with the API key and a custom logger.
        """
        self.api_key = api_key
        self.base_url = "http://local.adspower.net:50325"  
        self.logger = logger

    def _make_request(self, endpoint: str, method: str = "GET", params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make a request to the AdsPower API.
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            self.logger.info(f"Making GET request to : {url}")
            if method == "GET":
                response = requests.get(url, headers=headers, params=params)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            self.logger.info(f"Response: {response}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed: {e}")
            return None

    def check_browser_status(self, user_id: str) -> Optional[Dict]:
        """
        Check the status of a browser for a specific profile.
        """
        endpoint = "/api/v1/browser/active"
        params = {
            "user_id": user_id
        }

        self.logger.info(f"Checking browser status for profile: {user_id}")
        return self._make_request(endpoint, method="GET", params=params)

    def close_all_tabs(self, driver: webdriver.Remote) -> bool:
        """
        Close all tabs in the current browser instance except the first one.
        """
        try:
            # Get all window handles
            handles = driver.window_handles
            if len(handles) <= 1:
                self.logger.info("Only one tab is open. No tabs to close.")
                return True

            # Switch to the first tab and close all others
            driver.switch_to.window(handles[0])
            for handle in handles[1:]:
                driver.switch_to.window(handle)
                driver.close()
                self.logger.info(f"Closed tab with handle: {handle}")

            # Switch back to the first tab
            driver.switch_to.window(handles[0])
            self.logger.info("All additional tabs closed successfully.")
            return True

        except Exception as e:
            self.logger.error(f"Error closing tabs: {e}")
            return False

    def open_browser(self, user_id: str, proxy_config: Optional[Dict] = None) -> Optional[webdriver.Remote]:
        """
        Open a browser for a specific profile with optional proxy configuration.
        Returns a Selenium WebDriver instance if successful.
        """
        endpoint = "/api/v1/browser/start"
        params = {
            "user_id": user_id,
            "launch_args": None
        }

        if proxy_config:
            params["user_proxy_config"] = proxy_config

        self.logger.info(f"Opening browser for profile: {user_id} with proxy: {proxy_config}")
        response = self._make_request(endpoint, method="GET", params=params)

        if response and response.get("code") == 0:
            selenium_url = response["data"]["ws"]["selenium"]
            self.logger.info(f"Browser started successfully. Selenium URL: {selenium_url}")

            chrome_driver = response["data"]["webdriver"]
            self.logger.info(f"Chrome driver path: {chrome_driver}")
            self.logger.info("Display started")
            chrome_options = Options()
            chrome_options.add_experimental_option("debuggerAddress", response["data"]["ws"]["selenium"])
            service = Service(executable_path=chrome_driver)
            caps = DesiredCapabilities.CHROME
            caps['goog:loggingPrefs'] = {'performance': 'ALL'}
            driver = webdriver.Chrome(service=service, options=chrome_options, desired_capabilities=caps)
            time.sleep(3)
            self.logger.info("Driver started successfully")

            # Close all tabs except the first one
            self.close_all_tabs(driver)
            return driver
        else:
            self.logger.error(f"Failed to start browser: {response}")
            return None

    def close_browser(self, user_id: str) -> bool:
        """
        Close a browser for a specific profile.
        """
        try:
            # Check the browser status before closing
            status_response = self.check_browser_status(user_id)
            if status_response and status_response.get("code") == 0:
                if status_response.get("data", {}).get("status") == "Active":
                    endpoint = "/api/v1/browser/stop"
                    params = {
                        "user_id": user_id
                    }
                    close_response = self._make_request(endpoint, method="GET", params=params)
                    if close_response and close_response.get("code") == 0:
                        self.logger.info(f"Successfully closed browser for profile: {user_id}")
                        return True
                    else:
                        self.logger.error(f"Failed to close browser for profile: {user_id}")
                        return False
                else:
                    self.logger.info(f"Browser for profile {user_id} is already closed.")
                    return True
            else:
                self.logger.error(f"Failed to check browser status for profile: {user_id}")
                return False
        except Exception as e:
            self.logger.error(f"Error closing browser: {e}")
            return False

    def verify_proxy(self, driver: webdriver.Remote, expected_country: str) -> bool:
        """
        Verify that the proxy is working by checking the country using https://api.country.is/.
        """
        try:
            driver.get("https://api.country.is/")

            country = driver.find_element(By.TAG_NAME, "body").text.strip()
            data = json.loads(country)
            self.logger.info(data)
            
            country = data.get("country")
            if country == expected_country:
                self.logger.info(f"Proxy verification successful. Country: {country}")
                return True
            else:
                self.logger.warning(f"Proxy verification failed. Expected: {expected_country}, Got: {country}")
                return False

        except Exception as e:
            self.logger.error(f"Error verifying proxy: {e}")
            return False
