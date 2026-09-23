"""Load a policy page in a headless browser and return its visible text only.

Many policy pages are built with JavaScript, so a plain download returns an empty shell.
Security: we only ever keep the page's *visible text*. Scripts, HTML and links are thrown
away here and never reach the AI step or the web app.
"""
from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 PolicyDriftWatcher/0.1"
)
BLOCKED_RESOURCES = {"image", "media", "font"}

# Runs inside the page: drop menus, footers and cookie banners, then read the main text.
_EXTRACT_JS = """
() => {
  const drop = 'nav, header, footer, aside, script, style, noscript, iframe, svg, form, ' +
    '[role="navigation"], [role="banner"], [role="contentinfo"], [aria-modal="true"], ' +
    '[id*="cookie" i], [class*="cookie" i], [id*="consent" i], [class*="consent" i]';
  document.querySelectorAll(drop).forEach(el => el.remove());
  const candidates = [...document.querySelectorAll('main, article, [role="main"]')];
  const best = candidates.sort((a, b) => b.innerText.length - a.innerText.length)[0];
  const root = best && best.innerText.length > 2000 ? best : document.body;
  return root ? root.innerText : '';
}
"""


class FetchError(Exception):
    pass


class Browser:
    """One shared browser for the whole run."""

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    def page_text(self, url: str, timeout_ms: int = 45000) -> str:
        if not url.startswith("https://"):
            raise FetchError("only https:// pages are allowed")
        context = self._browser.new_context(
            user_agent=USER_AGENT,
            java_script_enabled=True,
            accept_downloads=False,
            locale="en-US",
        )
        try:
            page = context.new_page()
            page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in BLOCKED_RESOURCES
                else route.continue_(),
            )
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if response is None or response.status >= 400:
                raise FetchError(f"page returned HTTP {response.status if response else 'no response'}")
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass  # some pages never go fully idle; the text is usually there anyway
            return page.evaluate(_EXTRACT_JS) or ""
        finally:
            context.close()
