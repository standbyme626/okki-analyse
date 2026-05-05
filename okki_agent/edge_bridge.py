"""CDP bridge connection for Windows Edge browser.

Provides the live browser connection that writer.py and scripts depend on.
Also provides pagination helpers for the OKKI customer list page.

Usage:
    from okki_agent.edge_bridge import next_page, prev_page, _run, _eval

    next_page()  # -> (old_page, new_page)
    prev_page()  # -> (old_page, new_page)
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Tuple

_BRIDGE_HTTP = os.environ.get(
    "OKKI_BRIDGE_URL",
    "http://172.22.208.1:21002",
)
_ws_url: str | None = None


def _get_ws_url() -> str:
    """Fetch the CDP WebSocket URL from the bridge, cached per process."""
    global _ws_url
    if _ws_url:
        return _ws_url
    try:
        with urllib.request.urlopen(
            f"{_BRIDGE_HTTP}/json/version", timeout=5
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _ws_url = data["webSocketDebuggerUrl"]
        return _ws_url  # type: ignore[return-value]
    except Exception as e:
        raise RuntimeError(
            f"Failed to discover Edge CDP via bridge {_BRIDGE_HTTP}: {e}"
        ) from e


def _run(*args: str, timeout_sec: int = 30, **_kw: Any) -> str:
    """Run a raw agent-browser command against the Edge CDP bridge."""
    ws = _get_ws_url()
    cmd = ["agent-browser", "--cdp", ws, *args]
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_sec)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip())
    return (p.stdout or "").strip()


def _eval(js: str, timeout_sec: int = 30, **_kw: Any) -> Any:
    """Run JavaScript in the Edge browser and parse the result."""
    out = _run("eval", js, timeout_sec=timeout_sec).strip()
    if not out:
        return None
    if out.startswith('"'):
        out = json.loads(out)
    try:
        return json.loads(out)
    except (json.JSONDecodeError, TypeError):
        return out


def _get_current_page() -> int:
    """Read current active page number from the OKKI customer list pagination."""
    js = """(() => {
        const norm = s => (s || '').trim();
        const items = [...document.querySelectorAll('li')];
        // OKKI renders active page as an li with class containing 'active'
        const active = items.find(li =>
            li.className && li.className.includes && li.className.includes('active')
        );
        if (active) return parseInt(active.textContent, 10) || 0;
        // Fallback: check ant-design pagination active item
        const antActive = document.querySelector('.ant-pagination-item-active');
        if (antActive) return parseInt(antActive.textContent, 10) || 0;
        return 0;
    })()"""
    val = _eval(js)
    return int(val) if val else 0


def next_page(timeout_sec: float = 10.0) -> Tuple[int, int]:
    """Click '下一页' and poll until the page number changes.

    Returns (old_page, new_page). Raises RuntimeError on timeout.
    """
    old = _get_current_page()
    js = """(() => {
        const items = [...document.querySelectorAll('li')];
        const next = items.find(li => (li.textContent || '').includes('下一页'));
        if (!next) return 'NO_NEXT_PAGE';
        const btn = next.querySelector('button') || next;
        btn.click();
        return 'CLICKED_NEXT';
    })()"""
    result = str(_eval(js))
    if result == "NO_NEXT_PAGE":
        raise RuntimeError("Next page button not found")

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        time.sleep(0.5)
        cur = _get_current_page()
        if cur != old:
            return old, cur

    raise RuntimeError(
        f"Page did not change after click: still on page {old} after {timeout_sec:.0f}s"
    )


def prev_page(timeout_sec: float = 10.0) -> Tuple[int, int]:
    """Click '上一页' and poll until the page number changes.

    Returns (old_page, new_page). Raises RuntimeError if already on page 1 or timeout.
    """
    old = _get_current_page()
    if old <= 1:
        raise RuntimeError("Already on page 1, cannot go to previous page")

    js = """(() => {
        const items = [...document.querySelectorAll('li')];
        const prev = items.find(li => (li.textContent || '').includes('上一页'));
        if (!prev) return 'NO_PREV_PAGE';
        const btn = prev.querySelector('button');
        // button is disabled on page 1, but we already guard against that
        if (btn && btn.disabled) return 'PREV_DISABLED';
        (btn || prev).click();
        return 'CLICKED_PREV';
    })()"""
    result = str(_eval(js))
    if result in ("NO_PREV_PAGE", "PREV_DISABLED"):
        raise RuntimeError(f"Previous page not available: {result}")

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        time.sleep(0.5)
        cur = _get_current_page()
        if cur != old:
            return old, cur

    raise RuntimeError(
        f"Page did not change after click: still on page {old} after {timeout_sec:.0f}s"
    )
