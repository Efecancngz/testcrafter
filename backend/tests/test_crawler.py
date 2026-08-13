from pathlib import Path

from app.crawler import extract_page_structure, BotChallengeDetected
import pytest

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "login_page.html").as_uri()
CLOUDFLARE_FIXTURE_URL = (Path(__file__).parent / "fixtures" / "cloudflare_challenge.html").as_uri()
RECAPTCHA_FIXTURE_URL = (Path(__file__).parent / "fixtures" / "recaptcha_challenge.html").as_uri()


def test_extract_page_structure_finds_inputs_and_buttons():
    structure = extract_page_structure(FIXTURE_URL)

    roles = {el.role for el in structure.elements}
    assert "input" in roles
    assert "button" in roles
    assert "link" in roles

    submit_button = next(el for el in structure.elements if el.selector == "#submit")
    assert submit_button.text == "Log in"


def test_extract_page_structure_raises_on_cloudflare_challenge_title():
    with pytest.raises(BotChallengeDetected) as exc_info:
        extract_page_structure(CLOUDFLARE_FIXTURE_URL)
    assert exc_info.value.provider == "cloudflare"


def test_extract_page_structure_raises_on_recaptcha_iframe():
    with pytest.raises(BotChallengeDetected) as exc_info:
        extract_page_structure(RECAPTCHA_FIXTURE_URL)
    assert exc_info.value.provider == "recaptcha"
