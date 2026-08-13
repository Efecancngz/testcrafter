# Bot Challenge Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect known bot-verification challenge pages (Cloudflare, reCAPTCHA, hCaptcha) during crawl and stop the scan with a distinct `"blocked"` status instead of extracting garbage content from the challenge page.

**Architecture:** `crawler.py` gains signature-based detection (response header, page title, DOM markers) that raises a new `BotChallengeDetected` exception before element extraction runs. `scans.py` catches it in `create_scan`, persists a new `blocked_reason` column, and returns `status="blocked"`. The frontend shows a distinct message for that status.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Playwright (sync API), pytest, React.

## Global Constraints

- Comments only for non-obvious WHY, never WHAT (per `CLAUDE.md`).
- No speculative abstractions — this only needs to distinguish 3 providers, don't build a generic plugin system.
- User-facing errors are human-readable; stack traces stay in backend logs only.
- Never add a "Co-Authored-By: Claude" trailer to any commit (hard rule, `CLAUDE.md`).
- Schema changes go through Alembic (`alembic revision --autogenerate`), never manual migration edits (per `HANDOFF.md`'s documented workflow).
- Detection is signature-based only — no content-density heuristics (spec: `docs/superpowers/specs/2026-08-13-bot-challenge-detection-design.md`).
- English primary for user-facing copy (`CLAUDE.md` doc convention).

---

### Task 1: Crawler bot-challenge detection

**Files:**
- Modify: `backend/app/crawler.py`
- Create: `backend/tests/fixtures/cloudflare_challenge.html`
- Create: `backend/tests/fixtures/recaptcha_challenge.html`
- Test: `backend/tests/test_crawler.py`

**Interfaces:**
- Produces: `class BotChallengeDetected(Exception)` with a `.provider: str` attribute, importable as `from app.crawler import BotChallengeDetected`. Task 3 catches this exception by name.
- Produces: `extract_page_structure(url: str) -> PageStructure` keeps its existing signature; now additionally raises `BotChallengeDetected` for challenge pages instead of returning a `PageStructure`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_crawler.py` (the file already has `from pathlib import Path` and `from app.crawler import extract_page_structure` at the top — extend the import and add the fixture URL constants alongside the existing `FIXTURE_URL`):

```python
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
```

(The existing `test_extract_page_structure_finds_inputs_and_buttons` is shown above unchanged — it's the regression guard confirming non-challenge pages still extract normally. Don't duplicate it; just add the two new test functions plus the two new import lines to the existing file.)

Also create the two new fixture files:

`backend/tests/fixtures/cloudflare_challenge.html`:
```html
<!DOCTYPE html>
<html>
<head><title>Just a moment...</title></head>
<body>
  <div>Checking your browser before accessing the site.</div>
</body>
</html>
```

`backend/tests/fixtures/recaptcha_challenge.html`:
```html
<!DOCTYPE html>
<html>
<head><title>Verify you are human</title></head>
<body>
  <iframe src="https://www.google.com/recaptcha/api2/anchor?k=fake-test-key"></iframe>
</body>
</html>
```

- [ ] **Step 2: Run tests to verify the two new ones fail**

Run: `cd backend && pytest tests/test_crawler.py -v`
Expected: `test_extract_page_structure_raises_on_cloudflare_challenge_title` and
`test_extract_page_structure_raises_on_recaptcha_iframe` FAIL with
`ImportError: cannot import name 'BotChallengeDetected'` (or, once that's
fixed in a later sub-step, `Failed: DID NOT RAISE`). The existing
`test_extract_page_structure_finds_inputs_and_buttons` still PASSES
unchanged.

- [ ] **Step 3: Implement detection in `crawler.py`**

Replace the full contents of `backend/app/crawler.py` with:

```python
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
```

Note: `browser.close()` is not called on the `BotChallengeDetected` path,
matching the existing (pre-this-change) behavior where a `PlaywrightError`
from `page.goto()` also skips it — the `with sync_playwright() as p:`
block's exit still tears down the driver. This is an existing pattern in
this file, not a regression introduced here.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_crawler.py -v`
Expected: all tests PASS, including the pre-existing
`test_extract_page_structure_finds_inputs_and_buttons`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/crawler.py backend/tests/test_crawler.py backend/tests/fixtures/cloudflare_challenge.html backend/tests/fixtures/recaptcha_challenge.html
git commit -m "feat: detect Cloudflare/reCAPTCHA/hCaptcha challenge pages in crawler"
```

---

### Task 2: `blocked_reason` column + migration

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/<autogenerated>.py` (filename determined by Alembic at generation time)
- Modify: `docs/data-model.md`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `Scan.blocked_reason: str | None` column, consumed by Task 3's `scans.py` changes (`scan.blocked_reason = e.provider`) and by the `ScanOut` schema Task 3 defines.

- [ ] **Step 1: Confirm the existing schema-drift test currently passes**

Run: `cd backend && pytest tests/test_alembic.py -v`
Expected: PASS (this establishes the baseline — the next step's failure is
caused by your model change, not something pre-existing).

- [ ] **Step 2: Add the column to `models.py`**

In `backend/app/models.py`, the `Scan` class currently ends with:
```python
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
```
Change it to:
```python
    status: Mapped[str] = mapped_column(String, default="pending")
    blocked_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
```

- [ ] **Step 3: Run the schema-drift test to verify it now fails**

Run: `cd backend && pytest tests/test_alembic.py -v`
Expected: FAIL — `compare_metadata` reports a diff containing an added
column `blocked_reason` on table `scans` (this is `test_alembic.py`'s
existing `assert diff == []`, no new test code needed; the model change
alone is what breaks it).

- [ ] **Step 4: Generate the migration**

Run: `cd backend && alembic revision --autogenerate -m "add scan blocked_reason column"`

This creates a new file under `backend/alembic/versions/`. Open it and
verify the `upgrade()` function contains exactly one operation:
```python
op.add_column('scans', sa.Column('blocked_reason', sa.String(), nullable=True))
```
and `downgrade()` contains the matching:
```python
op.drop_column('scans', 'blocked_reason')
```
Per this project's established workflow (`HANDOFF.md`), do not hand-edit
the generated file beyond verifying it — if it contains anything other
than this single column add/drop, stop and report rather than editing it,
since that would indicate the autogenerate diffed against unexpected
state.

- [ ] **Step 5: Run the schema-drift test to verify it passes again**

Run: `cd backend && pytest tests/test_alembic.py -v`
Expected: PASS.

- [ ] **Step 6: Update `docs/data-model.md`**

Find the `Scan` table's status row (currently reads
`| status | string | \`pending\` \| \`analyzing\` \| \`ready\` \| \`failed\` |`)
and change it to:
```
| status | string | `pending` \| `analyzing` \| `ready` \| `failed` \| `blocked` |
```
Immediately below that row (still inside the `Scan` table's row list), add
a new row:
```
| blocked_reason | string \| null | Set only when status is `blocked`; identifies which provider's challenge was detected (`cloudflare` \| `recaptcha` \| `hcaptcha`) |
```

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && pytest`
Expected: all tests PASS (confirms the column addition didn't break
anything else, e.g. `test_models.py`).

- [ ] **Step 8: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/ docs/data-model.md
git commit -m "feat: add Scan.blocked_reason column via migration"
```

---

### Task 3: Wire detection into `create_scan` / `get_scan`

**Files:**
- Modify: `backend/app/api/scans.py`
- Modify: `docs/api-spec.md`
- Test: `backend/tests/test_api_scans.py`

**Interfaces:**
- Consumes: `from app.crawler import extract_page_structure, BotChallengeDetected` (Task 1) and `Scan.blocked_reason` (Task 2).
- Produces: `ScanOut` schema gains `blocked_reason: str | None = None`, returned by both `create_scan` and `get_scan`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_api_scans.py`. The file already imports
`from playwright.sync_api import Error as PlaywrightError` and
`from unittest.mock import patch` — add one more import line at the top:

```python
from app.crawler import BotChallengeDetected
```

Then add these two test functions (placed after
`test_create_scan_marks_failed_when_crawl_fails`, following that test's
existing style):

```python
def test_create_scan_marks_blocked_when_bot_challenge_detected(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    with patch("app.api.scans.extract_page_structure", side_effect=BotChallengeDetected("cloudflare")), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "blocked"
    assert body["blocked_reason"] == "cloudflare"
    assert body["scenarios"] == []
    mock_get_provider.assert_not_called()


def test_get_scan_includes_blocked_reason(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    with patch("app.api.scans.extract_page_structure", side_effect=BotChallengeDetected("recaptcha")):
        scan = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "x",
        }).json()

    resp = authenticated_client.get(f"/scans/{scan['id']}")

    assert resp.status_code == 200
    assert resp.json()["blocked_reason"] == "recaptcha"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_api_scans.py -v`
Expected: both new tests FAIL — `BotChallengeDetected` currently propagates
as an unhandled exception (500), and `ScanOut` has no `blocked_reason`
field yet.

- [ ] **Step 3: Implement the API changes**

In `backend/app/api/scans.py`:

1. Change the import line
   ```python
   from app.crawler import extract_page_structure
   ```
   to
   ```python
   from app.crawler import extract_page_structure, BotChallengeDetected
   ```

2. Add `blocked_reason` to the `ScanOut` class:
   ```python
   class ScanOut(BaseModel):
       id: int
       target_url: str
       status: str
       blocked_reason: str | None = None
       scenarios: list[ScenarioOut]
   ```

3. In `create_scan`, the current crawl try/except is:
   ```python
       try:
           page_structure = extract_page_structure(payload.target_url)
       except PlaywrightError:
           # Bad/unreachable target_url is external input, not a bug in our code —
           # record the scan as failed instead of a 500, per docs/api-spec.md.
           logger.exception("crawl failed for scan %s (%s)", scan.id, payload.target_url)
           scan.status = "failed"
           session.commit()
           session.refresh(scan)
           return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, scenarios=[])
   ```
   Add a new `except BotChallengeDetected` branch **before** the
   `except PlaywrightError` branch (order matters here only for readability
   — the two exception types are unrelated, `BotChallengeDetected` extends
   `Exception` directly, not `PlaywrightError`, so either order behaves
   identically):
   ```python
       try:
           page_structure = extract_page_structure(payload.target_url)
       except BotChallengeDetected as e:
           logger.info("bot challenge detected for scan %s (%s): %s", scan.id, payload.target_url, e.provider)
           scan.status = "blocked"
           scan.blocked_reason = e.provider
           session.commit()
           session.refresh(scan)
           return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, blocked_reason=scan.blocked_reason, scenarios=[])
       except PlaywrightError:
           # Bad/unreachable target_url is external input, not a bug in our code —
           # record the scan as failed instead of a 500, per docs/api-spec.md.
           logger.exception("crawl failed for scan %s (%s)", scan.id, payload.target_url)
           scan.status = "failed"
           session.commit()
           session.refresh(scan)
           return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, scenarios=[])
   ```

4. `create_scan`'s final return (after the AI-provider try/except further
   down) already builds `ScanOut(id=scan.id, target_url=scan.target_url,
   status=scan.status, scenarios=scenarios)` — no change needed there, since
   `blocked_reason` defaults to `None` and that path can never set
   `scan.status = "blocked"`.

5. In `get_scan`, change:
   ```python
   return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, scenarios=scenarios)
   ```
   to:
   ```python
   return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, blocked_reason=scan.blocked_reason, scenarios=scenarios)
   ```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_api_scans.py -v`
Expected: all tests PASS, including the two new ones and every
pre-existing test in the file (in particular
`test_create_scan_marks_failed_when_crawl_fails`, to confirm the
`PlaywrightError` branch still works unchanged).

- [ ] **Step 5: Update `docs/api-spec.md`**

Find the existing sentence (near the `POST /projects/{project_id}/scans`
section):
```
If the AI response fails schema validation, the scan is saved with `status = "failed"` rather than the request erroring out — the crawl and scan record are still useful even if scenario generation failed.
```
Add a new sentence directly after it:
```
If the crawl detects a bot-verification challenge page (Cloudflare, reCAPTCHA, hCaptcha) instead of real content, the scan is saved with `status = "blocked"` and `blocked_reason` set to the detected provider name — scenario generation is never attempted against challenge-page content.
```

- [ ] **Step 6: Run the full backend test suite**

Run: `cd backend && pytest`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/scans.py backend/tests/test_api_scans.py docs/api-spec.md
git commit -m "feat: return blocked status and reason when scan crawl hits a bot challenge"
```

---

### Task 4: Frontend blocked-status display

**Files:**
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- Consumes: `scan.status === "blocked"` and `scan.blocked_reason` (string) from the `ScanOut` JSON Task 3 returns — no frontend API client changes needed since `frontend/src/api.js` already passes through whatever JSON the backend returns.

- [ ] **Step 1: Modify the status display block**

In `frontend/src/App.jsx`, find:
```jsx
      {scan && (
        <div>
          <h2>Status: {scan.status}</h2>
          <ul>
            {scan.scenarios.map((s) => (
              <li key={s.id}>{s.title}</li>
            ))}
          </ul>
          {scan.status === "ready" && (
            <button onClick={handleRun} disabled={running}>{running ? "Running..." : "Run scenarios"}</button>
          )}
        </div>
      )}
```
Replace it with:
```jsx
      {scan && (
        <div>
          <h2>Status: {scan.status}</h2>
          {scan.status === "blocked" && (
            <p style={{ color: "#b8860b" }}>
              This site uses {scan.blocked_reason} bot protection and couldn't be scanned.
            </p>
          )}
          <ul>
            {scan.scenarios.map((s) => (
              <li key={s.id}>{s.title}</li>
            ))}
          </ul>
          {scan.status === "ready" && (
            <button onClick={handleRun} disabled={running}>{running ? "Running..." : "Run scenarios"}</button>
          )}
        </div>
      )}
```

- [ ] **Step 2: Manually verify in the browser**

This project's frontend has no JS test framework (`frontend/package.json`
lists no test runner — consistent with its current minimal-dashboard
state). Verify manually instead:

Run: `cd backend && docker compose up` (or run the backend directly per
`CONTRIBUTING.md`), and `cd frontend && npm run dev`.

In the browser: log in, create a project, submit a scan whose target URL
is a page that will trigger the new `except BotChallengeDetected` branch.
Since no public site is guaranteed to reliably serve a matching challenge
page on demand, verify instead by temporarily pointing `target_url` at the
`cloudflare_challenge.html` fixture's `file://` URL from Task 1
(`(Path(__file__).parent / "fixtures" / "cloudflare_challenge.html").as_uri()`
printed via a one-off `python -c` — or simply reuse the fixture path
computed the same way `test_crawler.py` does) — confirm the dashboard
shows "Status: blocked" and the "This site uses cloudflare bot protection
and couldn't be scanned." message, then revert the manual test data (no
code change to revert, this only touches what you typed into the running
UI).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat: show a distinct message when a scan is blocked by a bot challenge"
```
