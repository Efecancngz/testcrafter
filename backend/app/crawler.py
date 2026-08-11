from playwright.sync_api import sync_playwright

from app.schemas import PageElement, PageStructure

_SELECTORS = {
    "input": "input",
    "button": "button, input[type=submit]",
    "link": "a[href]",
    "form": "form",
}


def extract_page_structure(url: str) -> PageStructure:
    elements: list[PageElement] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url)

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
