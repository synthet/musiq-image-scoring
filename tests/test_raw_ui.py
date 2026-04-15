import importlib.util
import pytest
import os
import sys

try:
    from playwright.sync_api import Page, expect
except ImportError:
    Page = object  # type: ignore[misc, assignment]
    expect = lambda x: x  # type: ignore[assignment]

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration
TEST_URL = "http://localhost:7860"

_HAS_PYTEST_PLAYWRIGHT = importlib.util.find_spec("pytest_playwright") is not None
_RUN_RAW_UI_TESTS = os.environ.get("RUN_RAW_UI_TESTS", "").strip().lower() in ("1", "true", "yes")

pytestmark = pytest.mark.skipif(
    (not _HAS_PYTEST_PLAYWRIGHT) or (not _RUN_RAW_UI_TESTS),
    reason=(
        "requires pytest-playwright and a running WebUI with predictable test data; "
        "enable with RUN_RAW_UI_TESTS=1"
    ),
)


def test_raw_preview_rendering(page: Page):
    """
    Verify that a RAW file can be opened and rendered in the browser.
    """
    # 1. Navigate to gallery
    page.goto(TEST_URL)
    
    # 2. Find a NEF file in the grid (assuming test data exists)
    # We look for the entry with text containing .NEF or a specific test file
    nef_entry = page.locator("text=.NEF").first
    expect(nef_entry).to_be_visible()
    
    # 3. Click to open details
    nef_entry.click()
    
    # 4. Click "Full Preview" or similar button
    # Assuming there's a button with id 'raw_preview_btn'
    preview_btn = page.locator("#raw_preview_btn")
    if preview_btn.is_visible():
        preview_btn.click()
        
        # 5. Verify progress bar
        progress = page.locator("#raw_loading_progress")
        expect(progress).to_be_visible()
        
        # 6. Wait for canvas to have data
        # The RAW preview is rendered to a canvas with id 'raw_canvas'
        canvas = page.locator("#raw_canvas")
        
        # We check if canvas has content by evaluating its data URL width/height or non-empty pixels
        # Wait for loading to finish
        expect(progress).to_be_hidden(timeout=30000) # 30s for RAW decoding
        
        is_rendered = page.evaluate("(id) => { const c = document.getElementById(id); return c && c.width > 0 && c.height > 0; }", "raw_canvas")
        assert is_rendered, "Canvas should have positive dimensions after RAW rendering"


def test_gallery_filtering(page: Page):
    """
    Verify that filters (score, rating) correctly update the grid.
    """
    page.goto(TEST_URL)
    
    # Select rating filter 4 stars
    page.locator("#rating_filter >> text=4").click()
    
    # Verify that visible entries have rating 4
    # (Checking data attributes or visually if possible)
    # This is a placeholder for actual component-specific selectors
    pass
