import os

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from app.schemas import PageElement, PageStructure

# Some networks (corporate proxies, DPI middleboxes, certain ISPs) silently
# break Chromium's HTTP/2 connections to particular hosts, leaving page.goto()
# to hang until it times out. Those same hosts load fine over HTTP/1.1, so we
# turn HTTP/2 off rather than let a whole scan fail on a network quirk the user
# can't control. Costs a little throughput; buys reliability.
_BROWSER_ARGS = ["--disable-http2"]

# Wait only for the DOM, not for every image/iframe/analytics beacon the page
# pulls in. Element extraction needs a parsed DOM and nothing more, and heavy
# real-world sites routinely never reach the "load" event within any sane
# budget.
_WAIT_UNTIL = "domcontentloaded"

_NAVIGATION_TIMEOUT_MS = int(os.getenv("CRAWLER_TIMEOUT_MS", "30000"))

# After the DOM is ready, give client-rendered pages a brief chance to paint
# their real content before we snapshot the elements. Best-effort: sites with
# long-polling or persistent connections never go idle, so a miss here is
# expected and must not fail the crawl.
_SETTLE_TIMEOUT_MS = 3000

_SELECTORS = {
    "input": "input",
    "button": "button, input[type=submit]",
    "link": "a[href]",
    "form": "form",
}

_TITLE_SIGNATURES = {
    "Just a moment...": "cloudflare",
    "Attention Required! | Cloudflare": "cloudflare",
}

_DOM_SIGNATURES = [
    ("#challenge-form, #challenge-running", "cloudflare"),
    ("iframe[src*='challenges.cloudflare.com']", "cloudflare"),
]


class BotChallengeDetected(Exception):
    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(f"bot challenge detected: {provider}")


def _detect_bot_challenge(page, response) -> str | None:
    # cf-mitigated is Cloudflare's own header for pages it intercepted —
    # checked first since it needs no DOM/title heuristics at all.
    if response is not None and response.header_value("cf-mitigated"):
        return "cloudflare"
    title = page.title()
    if title in _TITLE_SIGNATURES:
        return _TITLE_SIGNATURES[title]
    for selector, provider in _DOM_SIGNATURES:
        if page.query_selector(selector) is not None:
            return provider
    return None


def extract_page_structure(url: str) -> PageStructure:
    elements: list[PageElement] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_BROWSER_ARGS)
        try:
            page = browser.new_page()
            response = page.goto(url, wait_until=_WAIT_UNTIL, timeout=_NAVIGATION_TIMEOUT_MS)
            try:
                page.wait_for_load_state("networkidle", timeout=_SETTLE_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                pass

            provider = _detect_bot_challenge(page, response)
            if provider is not None:
                raise BotChallengeDetected(provider)

            for role, css in _SELECTORS.items():
                for i, handle in enumerate(page.query_selector_all(css)):
                    el_id = handle.get_attribute("id")
                    selector = f"#{el_id}" if el_id else f"{css} >> nth={i}"
                    elements.append(
                        PageElement(
                            tag=handle.evaluate("el => el.tagName.toLowerCase()"),
                            role=role,
                            selector=selector,
                            text=handle.text_content(),
                        )
                    )
        finally:
            browser.close()
    return PageStructure(url=url, elements=elements)
