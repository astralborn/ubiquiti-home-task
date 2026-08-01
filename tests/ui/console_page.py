"""Page object for the RustFS web console."""

from __future__ import annotations

import logging

from playwright.sync_api import Page, expect

from tests.constants import (
    RUSTFS_ACCESS_KEY,
    RUSTFS_CONSOLE_URL,
    RUSTFS_SECRET_KEY,
)

logger = logging.getLogger(__name__)


class ConsolePage:
    """Wraps Playwright interactions with the RustFS console.

    :param page: Playwright page instance.
    """

    def __init__(self, page: Page) -> None:
        self._page = page

    def login(
        self,
        access_key: str = RUSTFS_ACCESS_KEY,
        secret_key: str = RUSTFS_SECRET_KEY,
    ) -> None:
        """Fill credentials and submit the login form.

        :param access_key: Access key to enter.
        :param secret_key: Secret key to enter.
        """
        self._page.goto(RUSTFS_CONSOLE_URL)
        self._page.locator("#accessKey").fill(access_key)
        self._page.locator("#secretKey").fill(secret_key)
        self._page.locator("button[type='submit']").click()
        self._page.wait_for_url(
            lambda url: "/login" not in url,
            timeout=15_000,
            wait_until="networkidle",
        )
        logger.debug("Login complete, URL: %s", self._page.url)

    @property
    def is_logged_in(self) -> bool:
        """Check whether the current URL is past the login page."""
        return "/login" not in self._page.url

    def open_browser(self) -> None:
        """Navigate to the object browser view."""
        self._page.goto(f"{RUSTFS_CONSOLE_URL}/rustfs/console/browser")
        self._page.wait_for_load_state("networkidle")
        logger.debug("Browser view loaded, URL: %s", self._page.url)

    def create_bucket(self, name: str) -> None:
        """Create a bucket through the UI dialog.

        :param name: Bucket name to enter.
        """
        self._page.get_by_role("button", name="Create Bucket").click()
        self._page.locator("#bucket-name").fill(name)
        self._page.get_by_role("button", name="Create", exact=True).click()
        self._page.wait_for_timeout(1000)
        logger.debug("Create bucket dialog submitted for '%s'", name)

    def expect_bucket_visible(self, name: str, timeout: int = 5000) -> None:
        """Assert that a bucket name appears in the UI.

        :param name: Bucket name to look for.
        :param timeout: Maximum wait in milliseconds.
        """
        expect(self._page.get_by_text(name)).to_be_visible(timeout=timeout)
