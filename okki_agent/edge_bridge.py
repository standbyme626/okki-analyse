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
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Literal, Tuple

_BRIDGE_HTTP = os.environ.get(
    "OKKI_BRIDGE_URL",
    "http://172.22.208.1:21002",
)
_ws_url: str | None = None
RunFn = Callable[..., str]
EvalFn = Callable[..., Any]


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


def wait_ms(ms: int, *, run_fn: RunFn | None = None) -> None:
    """Wait inside the active browser page."""
    timeout_sec = max(5, int(ms / 1000) + 5)
    runner = run_fn or _run
    runner("wait", str(ms), timeout_sec=timeout_sec)


def get_url(timeout_sec: int = 10, *, run_fn: RunFn | None = None) -> str:
    runner = run_fn or _run
    return runner("get", "url", timeout_sec=timeout_sec)


def get_title(timeout_sec: int = 10, *, run_fn: RunFn | None = None) -> str:
    runner = run_fn or _run
    return runner("get", "title", timeout_sec=timeout_sec)


def snapshot_i(timeout_sec: int = 20, *, run_fn: RunFn | None = None) -> str:
    runner = run_fn or _run
    return runner("snapshot", "-i", timeout_sec=timeout_sec)


def _page_probe(*, eval_fn: EvalFn | None = None) -> Dict[str, Any]:
    js = """(() => {
        const norm = s => (s || '').replace(/\\s+/g, ' ').trim();
        const text = norm(document.body ? document.body.innerText : '');
        const buttons = [...document.querySelectorAll('button')]
            .map(btn => norm(btn.innerText || btn.textContent || ''))
            .filter(Boolean);
        const bodyRect = document.body
            ? document.body.getBoundingClientRect()
            : { width: 0, height: 0 };
        return JSON.stringify({
            ready_state: document.readyState || '',
            visibility_state: document.visibilityState || '',
            url: location.href,
            title: document.title || '',
            text_len: text.length,
            text_head: text.slice(0, 240),
            body_child_count: document.body ? document.body.children.length : 0,
            body_width: Math.round(bodyRect.width || 0),
            body_height: Math.round(bodyRect.height || 0),
            has_loading_mask: Boolean(document.querySelector(
                '.okki-spin-spinning,.ant-spin-spinning,.okki-loading,.loading,[aria-busy="true"]'
            )),
            has_detail_title: text.includes('客户详情'),
            has_edit_button: buttons.some(
                text => text === '编 辑' || text === '编辑' || text.replace(/\\s+/g, '') === '编辑'
            ),
            has_profile_tab: text.includes('资料'),
            has_common_section: text.includes('公司常用信息'),
            has_other_section: text.includes('公司其他信息'),
            has_detail_summary: text.includes('客户阶段')
                || text.includes('标签：')
                || text.includes('标签:')
                || text.includes('AI 客户分析')
                || text.includes('AI客户分析'),
            has_list_landmark: text.includes('客户列表')
                || text.includes('最近联系时间')
                || text.includes('国家地区'),
        });
    })()"""
    evaluator = eval_fn or _eval
    probe = evaluator(js, timeout_sec=10)
    if isinstance(probe, dict):
        return probe
    return {"probe_raw": probe}


def _is_probe_ready(
    probe: Dict[str, Any],
    page_kind: Literal["detail", "list", "generic"],
) -> bool:
    if probe.get("ready_state") != "complete":
        return False
    if probe.get("has_loading_mask"):
        return False
    if int(probe.get("body_width") or 0) < 240:
        return False
    if int(probe.get("body_height") or 0) < 240:
        return False
    if int(probe.get("text_len") or 0) < 80:
        return False

    url = str(probe.get("url") or "")
    title = str(probe.get("title") or "")

    if page_kind == "detail":
        on_detail_route = "/crm/customer/personal" in url or "客户详情" in title
        has_detail_landmark = any(
            [
                bool(probe.get("has_edit_button")),
                bool(probe.get("has_profile_tab")),
                bool(probe.get("has_common_section")),
                bool(probe.get("has_other_section")),
                bool(probe.get("has_detail_summary")),
                bool(probe.get("has_detail_title")),
            ]
        )
        return on_detail_route and has_detail_landmark

    if page_kind == "list":
        on_list_route = "/crm/customer/list" in url or "客户列表" in title
        return on_list_route and bool(probe.get("has_list_landmark"))

    return True


def wait_for_page_stable(
    page_kind: Literal["detail", "list", "generic"] = "detail",
    timeout_sec: int = 20,
    stable_rounds: int = 2,
    poll_interval_sec: float = 1.0,
    *,
    eval_fn: EvalFn | None = None,
) -> Tuple[bool, Dict[str, Any], List[Dict[str, Any]]]:
    """Wait until the active page is stable enough for screenshots."""
    deadline = time.monotonic() + timeout_sec
    ready_hits = 0
    last_probe: Dict[str, Any] = {}
    history: List[Dict[str, Any]] = []

    while time.monotonic() < deadline:
        probe = _page_probe(eval_fn=eval_fn)
        probe["page_kind"] = page_kind
        probe["ready"] = _is_probe_ready(probe, page_kind)
        history.append(probe)
        last_probe = probe

        if probe["ready"]:
            ready_hits += 1
            if ready_hits >= max(1, stable_rounds):
                return True, probe, history
        else:
            ready_hits = 0

        time.sleep(poll_interval_sec)

    return False, last_probe, history


def capture_checkpoint(
    screenshot_path: str | Path,
    *,
    snapshot_path: str | Path | None = None,
    probe_path: str | Path | None = None,
    page_kind: Literal["detail", "list", "generic"] = "detail",
    timeout_sec: int = 20,
    stable_rounds: int = 2,
    settle_ms: int = 800,
    capture_when_unready: bool = False,
    run_fn: RunFn | None = None,
    eval_fn: EvalFn | None = None,
) -> Dict[str, Any]:
    """Capture screenshot evidence only after the page reaches a stable state."""
    runner = run_fn or _run
    ready, probe, history = wait_for_page_stable(
        page_kind=page_kind,
        timeout_sec=timeout_sec,
        stable_rounds=stable_rounds,
        eval_fn=eval_fn,
    )

    result: Dict[str, Any] = {
        "page_kind": page_kind,
        "ready": ready,
        "captured": False,
        "probe": probe,
        "probe_history": history,
    }

    if ready and settle_ms > 0:
        wait_ms(settle_ms, run_fn=runner)

    if snapshot_path is not None:
        snap_out = Path(snapshot_path)
        snap_out.parent.mkdir(parents=True, exist_ok=True)
        try:
            snap_out.write_text(
                snapshot_i(timeout_sec=30, run_fn=runner) + "\n",
                encoding="utf-8",
            )
            result["snapshot_path"] = str(snap_out)
        except Exception as exc:
            result["snapshot_error"] = str(exc)

    if not ready and not capture_when_unready:
        return result

    shot_out = Path(screenshot_path)
    shot_out.parent.mkdir(parents=True, exist_ok=True)
    try:
        runner("screenshot", str(shot_out), timeout_sec=60)
        result["captured"] = True
        result["screenshot_path"] = str(shot_out)
    except Exception as exc:
        result["screenshot_error"] = str(exc)

    if probe_path is not None:
        probe_out = Path(probe_path)
        probe_out.parent.mkdir(parents=True, exist_ok=True)
        probe_out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["probe_path"] = str(probe_out)
    return result


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
