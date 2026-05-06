#!/usr/bin/env python3
"""Read-only OKKI single-customer probe script.

Safety:
- Reads only (no save/submit/write actions)
- Handles one customer at a time
- Outputs proposed tags only
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from okki_agent.edge_bridge import capture_checkpoint


def run_cmd(cmd: list[str], timeout_sec: int = 20) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    if p.returncode != 0:
        raise RuntimeError(
            f"Command failed ({p.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        )
    return p.stdout.strip()


class AgentBrowser:
    def __init__(self, session: str | None, cdp: str | None):
        self.base = ["agent-browser"]
        if cdp:
            self.base += ["--cdp", cdp]
        elif session:
            self.base += ["--session", session]

    def run(self, *args: str, timeout_sec: int = 20) -> str:
        return run_cmd(self.base + list(args), timeout_sec=timeout_sec)

    def eval(self, js: str, timeout_sec: int = 20) -> Any:
        raw = self.run("eval", js, timeout_sec=timeout_sec).strip()
        if not raw:
            return None
        if raw.startswith('"'):
            raw = json.loads(raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def ensure_dirs() -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    Path("screenshots").mkdir(parents=True, exist_ok=True)


def save_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def extract_panel_data(snapshot_c: str) -> dict[str, Any]:
    customer_code = None
    m = re.search(r"StaticText \"(NA_[A-Za-z0-9_]+)\"", snapshot_c)
    if m:
        customer_code = m.group(1)

    # Owner: look for "跟进人:" then next StaticText line.
    owner = None
    lines = snapshot_c.splitlines()
    for i, line in enumerate(lines):
        if 'StaticText "跟进人:"' in line:
            for j in range(i + 1, min(i + 8, len(lines))):
                m2 = re.search(r'StaticText "([^"]+)"', lines[j])
                if m2 and m2.group(1) != "跟进人:":
                    owner = m2.group(1)
                    break
            break

    # Existing tags around "标签：" (often empty in this UI).
    existing_tags: list[str] = []
    for i, line in enumerate(lines):
        if 'StaticText "标签："' in line:
            for j in range(i + 1, min(i + 10, len(lines))):
                if 'StaticText "跟进人:"' in lines[j]:
                    break
                m3 = re.search(r'StaticText "([^"]+)"', lines[j])
                if not m3:
                    continue
                value = m3.group(1).strip()
                if value and value not in {"标签：", "跟进人:", "--"}:
                    existing_tags.append(value)
            break

    # Lightweight field extraction from visible profile text.
    emails = sorted(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", snapshot_c)))
    country = None
    m_country = re.search(r'StaticText "([\u4e00-\u9fffA-Za-z ]+)"\n\s*- StaticText "\d{2}:\d{2} UTC', snapshot_c)
    if m_country:
        country = m_country.group(1).strip()

    timezone = None
    m_tz = re.search(r'StaticText "(\d{2}:\d{2} UTC[+-]?\d*)"', snapshot_c)
    if m_tz:
        timezone = m_tz.group(1)

    return {
        "customer_code": customer_code,
        "owner": owner,
        "existing_tags": existing_tags,
        "emails": emails,
        "country": country,
        "timezone": timezone,
    }


def propose_tags(data: dict[str, Any]) -> list[str]:
    tags: list[str] = []

    if not data.get("existing_tags"):
        tags.append("标签待完善")
    if data.get("emails"):
        tags.append("已识别邮箱")
    else:
        tags.append("邮箱待补全")
    if data.get("country"):
        tags.append(f"国家:{data['country']}")
    if data.get("timezone"):
        tags.append(f"时区:{data['timezone']}")
    if data.get("owner"):
        tags.append("已分配跟进人")

    # unique, preserve order
    seen = set()
    out = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def web_enrich(company_or_email: str, limit: int = 3) -> list[dict[str, str]]:
    q = urllib.parse.quote(company_or_email)
    url = f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&no_redirect=1"
    req = urllib.request.Request(url, headers={"User-Agent": "okki-probe/1.0"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))

    out: list[dict[str, str]] = []
    abstract = (payload.get("AbstractText") or "").strip()
    if abstract:
        out.append({"source": "duckduckgo_abstract", "text": abstract[:500]})

    for item in payload.get("RelatedTopics", [])[:limit]:
        if isinstance(item, dict) and item.get("Text"):
            out.append({"source": "duckduckgo_related", "text": str(item["Text"])[:500]})
    return out


def maybe_open_detail(ab: AgentBrowser, customer_name: str | None) -> None:
    snap = ab.run("snapshot", "-c")
    if 'StaticText "客户详情"' in snap and 'StaticText "标签："' in snap:
        return

    if not customer_name:
        raise RuntimeError(
            "Not on customer detail panel. Provide --customer-name to open one customer from list."
        )

    # Search and open one customer detail panel.
    ab.run("find", "placeholder", "请输入搜索关键字", "fill", customer_name)
    ab.run("press", "Enter")
    ab.run("wait", "1200")

    js_click = (
        "(() => {"
        "const name=" + json.dumps(customer_name) + ";"
        "const nodes=[...document.querySelectorAll('span,p,div')];"
        "const el=nodes.find(n=>(n.textContent||'').trim()===name);"
        "if(!el){return 'NOT_FOUND';}"
        "el.click();"
        "return 'CLICKED';"
        "})()"
    )
    ab.run("eval", js_click)
    ab.run("wait", "1000")

    snap2 = ab.run("snapshot", "-c")
    if 'StaticText "客户详情"' not in snap2:
        raise RuntimeError("Could not open customer detail panel from current list state.")


def ensure_profile_tab(ab: AgentBrowser) -> None:
    snap = ab.run("snapshot", "-c")
    if 'tab "资料" [selected' in snap:
        return
    ab.run("find", "text", "资料", "click")
    ab.run("wait", "700")


def main() -> int:
    ap = argparse.ArgumentParser(description="OKKI single-customer read-only probe")
    ap.add_argument("--session", default="okki", help="agent-browser session name")
    ap.add_argument("--cdp", default=None, help="optional CDP endpoint/port")
    ap.add_argument("--customer-name", default=None, help="single test customer name")
    ap.add_argument("--web-enrich", action="store_true", help="query DuckDuckGo API for enrichment hints")
    ap.add_argument("--output", default="logs/probe_okki_customer.json", help="output json path")
    args = ap.parse_args()

    ensure_dirs()
    ab = AgentBrowser(session=args.session, cdp=args.cdp)

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    artifact_prefix = f"probe_okki_customer_{ts}"

    url = ab.run("get", "url")
    title = ab.run("get", "title")

    maybe_open_detail(ab, args.customer_name)
    ensure_profile_tab(ab)

    snapshot_i = ab.run("snapshot", "-i")
    snapshot_c = ab.run("snapshot", "-c")

    snap_i_path = Path(f"logs/{artifact_prefix}.snapshot_i.txt")
    snap_c_path = Path(f"logs/{artifact_prefix}.snapshot_c.txt")
    shot_path = Path(f"screenshots/{artifact_prefix}.png")
    shot_probe_path = Path(f"logs/{artifact_prefix}.ready.json")

    save_text(snap_i_path, snapshot_i + "\n")
    save_text(snap_c_path, snapshot_c + "\n")
    shot_meta = capture_checkpoint(
        shot_path,
        snapshot_path=snap_i_path,
        probe_path=shot_probe_path,
        page_kind="detail",
        timeout_sec=25,
        stable_rounds=2,
        settle_ms=800,
        run_fn=ab.run,
        eval_fn=ab.eval,
    )

    data = extract_panel_data(snapshot_c)
    proposed = propose_tags(data)

    enrich_target = None
    enrich_hits: list[dict[str, str]] = []
    if args.web_enrich:
        if data.get("emails"):
            enrich_target = data["emails"][0]
        elif data.get("customer_code"):
            enrich_target = data["customer_code"]

        if enrich_target:
            try:
                enrich_hits = web_enrich(enrich_target)
            except Exception as e:  # noqa: BLE001
                enrich_hits = [{"source": "duckduckgo_error", "text": str(e)}]

    result = {
        "timestamp": ts,
        "mode": "dry_run_read_only",
        "allow_write": False,
        "url": url,
        "title": title,
        "customer_name_input": args.customer_name,
        "customer_code": data.get("customer_code"),
        "owner": data.get("owner"),
        "country": data.get("country"),
        "timezone": data.get("timezone"),
        "emails": data.get("emails"),
        "existing_tags": data.get("existing_tags"),
        "proposed_tags": proposed,
        "would_add_tags": [t for t in proposed if t not in (data.get("existing_tags") or [])],
        "web_enrich_enabled": args.web_enrich,
        "web_enrich_target": enrich_target,
        "web_enrich_hits": enrich_hits,
        "artifacts": {
            "snapshot_i": str(snap_i_path),
            "snapshot_c": str(snap_c_path),
            "screenshot": shot_meta.get("screenshot_path"),
            "checkpoint_probe": str(shot_probe_path),
            "checkpoint_meta": shot_meta,
        },
        "note": "No save/submit/write actions executed.",
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_path = Path("logs/probe_okki_customer.latest.json")
    latest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
