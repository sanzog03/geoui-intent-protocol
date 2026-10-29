"""A Playwright-over-CDP session to a page that exposes ``window.geoui``.

Chromium is launched elsewhere with ``--remote-debugging-port`` (see
``demo/chromium.sh``); this module only attaches to it. Every call is one
``page.evaluate`` against the SDK's bridge: ``describe()``, ``getState()``
and ``render(intent)``. The page's ``render`` never throws (failures come
back as ``{ok: false, code, error}``), so a JS exception here means a bug
and surfaces as :class:`BridgeError`; a refused intent surfaces as
``ValueError`` carrying the page's message, which the tool layer hands back
to the agent.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

DEFAULT_CDP_ENDPOINT = "http://localhost:9222"

READY_EXPR = "() => window.geoui?.ready === true"
DESCRIBE_EXPR = "() => window.geoui.describe()"
GET_STATE_EXPR = "() => window.geoui.getState()"
RENDER_EXPR = "(intent) => window.geoui.render(intent)"


class BridgeError(RuntimeError):
    """No Chromium, no GeoUI page, or the page's bridge misbehaved. Not something the agent can fix."""


@dataclass(frozen=True)
class BridgeConfig:
    """Where the browser is and which page to use."""

    cdp_endpoint: str = DEFAULT_CDP_ENDPOINT
    #: Opened in a new tab when no page with a ready ``window.geoui`` is found; also used to
    #: prefer the page at this origin when several are ready.
    app_url: str | None = None
    ready_timeout_s: float = 10.0


def config_from_env(environ: Mapping[str, str] | None = None) -> BridgeConfig:
    """``PLAYWRIGHT_CDP_ENDPOINT`` (default ``http://localhost:9222``) and ``GEOUI_APP_URL``."""
    env = os.environ if environ is None else environ
    return BridgeConfig(
        cdp_endpoint=env.get("PLAYWRIGHT_CDP_ENDPOINT") or DEFAULT_CDP_ENDPOINT,
        app_url=env.get("GEOUI_APP_URL") or None,
    )


@runtime_checkable
class GeoUISession(Protocol):
    """What the tool layer needs from a page: the three bridge calls. ``BridgeSession`` and test fakes satisfy it."""

    async def describe(self) -> dict[str, Any]: ...

    async def get_state(self) -> dict[str, Any]: ...

    async def render(self, intent: dict[str, Any]) -> dict[str, Any]: ...


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class BridgeSession:
    """One Playwright connection to the browser; ``open`` before use, ``close`` after (or use :func:`bridge`)."""

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self._playwright: Any = None
        self._browser: Any = None

    @property
    def connected(self) -> bool:
        return bool(self._browser is not None and self._browser.is_connected())

    async def open(self) -> None:
        from playwright.async_api import Error, async_playwright

        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(self.config.cdp_endpoint)
        except Error as exc:
            await self.close()
            raise BridgeError(
                f"cannot attach to Chromium over CDP at {self.config.cdp_endpoint}: {exc.message.splitlines()[0]}"
            ) from exc

    async def close(self) -> None:
        browser, self._browser = self._browser, None
        playwright, self._playwright = self._playwright, None
        if browser is not None:
            await browser.close()  # disconnects; pages stay open in the browser
        if playwright is not None:
            await playwright.stop()

    async def page(self) -> Any:
        """The page to drive: at ``app_url``'s origin if ready, else any ready page, else a new tab at ``app_url``."""
        from playwright.async_api import Error

        if self._browser is None:
            raise BridgeError("session is not open")
        ready_pages = []
        for context in self._browser.contexts:
            for page in context.pages:
                try:
                    if await page.evaluate(READY_EXPR):
                        ready_pages.append(page)
                except Error:
                    continue  # closed or navigating
        if self.config.app_url:
            origin = _origin(self.config.app_url)
            for page in ready_pages:
                if page.url.startswith(origin):
                    return page
        if ready_pages:
            return ready_pages[0]
        if not self.config.app_url:
            raise BridgeError("no open page exposes window.geoui and GEOUI_APP_URL is not set, so none can be opened")
        context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(self.config.app_url)
            await page.wait_for_function(READY_EXPR, timeout=self.config.ready_timeout_s * 1000)
        except Error as exc:
            raise BridgeError(
                f"opened {self.config.app_url} but window.geoui did not become ready within "
                f"{self.config.ready_timeout_s:g}s: {exc.message.splitlines()[0]}"
            ) from exc
        return page

    async def evaluate(self, expression: str, arg: Any = None) -> Any:
        from playwright.async_api import Error

        page = await self.page()
        try:
            return await page.evaluate(expression, arg) if arg is not None else await page.evaluate(expression)
        except Error as exc:
            raise BridgeError(f"window.geoui call failed in the page: {exc.message.splitlines()[0]}") from exc

    async def describe(self) -> dict[str, Any]:
        return await self.evaluate(DESCRIBE_EXPR)

    async def get_state(self) -> dict[str, Any]:
        return await self.evaluate(GET_STATE_EXPR)

    async def render(self, intent: dict[str, Any]) -> dict[str, Any]:
        """Render; the page's ``{ok: false}`` answer becomes ``ValueError(error)`` for the agent."""
        result = await self.evaluate(RENDER_EXPR, intent)
        if not isinstance(result, dict) or "ok" not in result:
            raise BridgeError(f"window.geoui.render returned something that is not a RenderResult: {result!r:.200}")
        if not result["ok"]:
            raise ValueError(str(result.get("error") or result.get("code") or "render refused"))
        return result


@asynccontextmanager
async def bridge(config: BridgeConfig) -> AsyncIterator[BridgeSession]:
    """Open a session for one block of calls."""
    session = BridgeSession(config)
    await session.open()
    try:
        yield session
    finally:
        await session.close()


__all__ = [
    "DEFAULT_CDP_ENDPOINT",
    "DESCRIBE_EXPR",
    "GET_STATE_EXPR",
    "READY_EXPR",
    "RENDER_EXPR",
    "BridgeConfig",
    "BridgeError",
    "BridgeSession",
    "GeoUISession",
    "bridge",
    "config_from_env",
]
