from playwright.sync_api import sync_playwright

from app.schemas import PageElement, PageStructure

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
    ("iframe[src*='recaptcha']", "recaptcha"),
    ("iframe[src*='hcaptcha']", "hcaptcha"),
    ("[class*='cf-turnstile'], iframe[src*='challenges.cloudflare.com']", "cloudflare"),
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
        browser = p.chromium.launch()
        page = browser.new_page()
        response = page.goto(url)

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

        browser.close()
    return PageStructure(url=url, elements=elements)
