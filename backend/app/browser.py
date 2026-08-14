"""Shared Chromium launch and navigation settings.

The crawler and the runner each drive their own browser, and they previously
carried their own copies of these settings. That drift was a real bug: fixing a
navigation hang in the crawler left the runner still hanging on the same sites,
so a scan could be generated successfully and then fail at execution for a
reason that had already been fixed one file over. Both import from here now.
"""

import os

# Some networks (corporate proxies, DPI middleboxes, certain ISPs) silently
# break Chromium's HTTP/2 connections to particular hosts, leaving navigation to
# hang until it times out. Those same hosts load fine over HTTP/1.1, so we turn
# HTTP/2 off rather than let a scan fail on a network quirk the user can't
# control. Costs a little throughput; buys reliability.
BROWSER_ARGS = ["--disable-http2"]

# Wait only for the DOM, not for every image/iframe/analytics beacon the page
# pulls in. Both extracting elements and acting on them need a parsed DOM and
# nothing more, and heavy real-world sites routinely never reach the "load"
# event within any sane budget.
WAIT_UNTIL = "domcontentloaded"

NAVIGATION_TIMEOUT_MS = int(os.getenv("CRAWLER_TIMEOUT_MS", "30000"))

# After the DOM is ready, give client-rendered pages a brief chance to paint
# their real content. Best-effort: sites with long-polling or persistent
# connections never go idle, so a miss here is expected and must not fail.
SETTLE_TIMEOUT_MS = 3000
