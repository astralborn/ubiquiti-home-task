"""Focused browser UI test for the RustFS web console."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.conftest import unique_bucket_name
from tests.ui.console_page import ConsolePage


@pytest.mark.ui
def test_login_and_create_bucket(page: Page) -> None:
    """Console UI smoke test.

    Steps:
        1. Log in with root credentials.
        2. Verify the dashboard loads (no login redirect).
        3. Open the object browser view.
        4. Create a new bucket via the UI dialog.
        5. Verify the bucket name appears in the bucket list.
    """
    bucket_name = unique_bucket_name()
    console_page = ConsolePage(page)
    console_page.login()
    assert console_page.is_logged_in, "Login redirect detected — auth failed"

    console_page.open_browser()
    console_page.create_bucket(bucket_name)
    console_page.expect_bucket_visible(bucket_name)
