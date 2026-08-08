"""Screenshot the running app. `uv run python shot.py <out-prefix> [state]`.

States: `map` (as it opens), `search` (the suggestion list), `pick` (a mark tapped),
`closed`, `night`. Each is taken at desktop and phone size.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

URL = "http://localhost:8555"
SIZES = {"desktop": (1440, 900), "phone": (390, 844)}


def _search(page: Page, query: str) -> None:
    page.click(".st-key-finder input")
    page.type(".st-key-finder input", query, delay=40)
    page.wait_for_timeout(1200)


def _fly(page: Page, place: str) -> None:
    _search(page, place)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_timeout(6000)


def _tap_a_mark(page: Page, width: float, height: float) -> None:
    """Hover the grid until deck.gl puts up a tooltip, then tap that spot.

    Hovering first is not just for the screenshot: deck answers a click with the pick it
    resolved on the last pointer move, so a click with no move before it hits nothing.
    """
    for fx in (0.55, 0.6, 0.65, 0.7, 0.45, 0.5):
        for fy in (0.36, 0.42, 0.48, 0.3, 0.55):
            page.mouse.move(width * fx, height * fy)
            page.wait_for_timeout(300)
            tip = page.query_selector("#deckgl-wrapper .deck-tooltip")
            # deck keeps an empty tooltip node around, so its text is what says "a mark is
            # under the pointer". Not the harbour we flew to: the `map` shot has that card.
            name = tip.inner_text().strip() if tip else ""
            if name and "Concarneau" not in name:
                page.mouse.click(width * fx, height * fy)
                page.wait_for_timeout(9000)
                page.mouse.move(6, height - 6)  # a hovered mark keeps the canvas redrawing
                page.wait_for_timeout(1500)
                return
    raise AssertionError("no mark found to tap")


def _prepare(page: Page, state: str) -> None:
    if state == "search":
        _search(page, "Concarneau")
    elif state == "sheet":
        _fly(page, "Concarneau")
        page.mouse.move(40, 700)  # off the marks, so no hover tooltip hangs over the shot
    elif state == "pick":
        _fly(page, "Concarneau")
        box = page.locator("#deckgl-wrapper").bounding_box()
        assert box is not None
        _tap_a_mark(page, box["width"], box["height"])
    elif state == "closed":
        _fly(page, "Concarneau")
        box = page.locator("#deckgl-wrapper").bounding_box()
        assert box is not None
        page.mouse.click(box["width"] * 0.25, box["height"] * 0.8)
        page.wait_for_timeout(6000)
    elif state == "night":
        # `help=` makes Streamlit render the button twice, one copy collapsed to nothing.
        page.locator(".st-key-rail_night button:visible").first.click()
        page.wait_for_timeout(6000)
        page.mouse.move(10, 10)  # off the button, or its tooltip covers the rail
        page.wait_for_timeout(800)


def main() -> None:
    prefix = Path(sys.argv[1] if len(sys.argv) > 1 else "shots/shot")
    state = sys.argv[2] if len(sys.argv) > 2 else "map"
    prefix.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as play:
        browser = play.chromium.launch()
        for name, (width, height) in SIZES.items():
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(URL, wait_until="load", timeout=120_000)
            page.wait_for_timeout(9_000)
            _prepare(page, state)
            # deck.gl draws on its own clock; catch a frame boundary or the capture lands
            # halfway through one and half the marks come out half-painted.
            page.evaluate(
                "new Promise(go => requestAnimationFrame(() => requestAnimationFrame(go)))"
            )
            page.screenshot(path=f"{prefix}-{name}.png")
            page.close()
        browser.close()


main()
