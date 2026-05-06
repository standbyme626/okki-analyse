#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from okki_agent.edge_bridge import capture_checkpoint

AB = ["agent-browser", "--session", "okki"]
OUT_DIR = Path("logs/recon")
SHOT_DIR = Path("screenshots/recon")
OUT_DIR.mkdir(parents=True, exist_ok=True)
SHOT_DIR.mkdir(parents=True, exist_ok=True)

NAV_LINKS = {
    "常用",
    "工作台",
    "邮件",
    "沟通",
    "线索",
    "商机",
    "客户列表",
    "使用指南",
    "一站式获客",
    "智能获客",
    "推荐广场",
    "渠道获客",
    "搜索引擎",
    "智能贸易数据",
    "展会数据",
    "B2B询盘",
    "社媒数据",
    "地图获客",
    "动态监测",
    "社媒动态",
    "交易动态",
    "触达工具",
    "智能营销",
    "邮件营销",
    "WhatsApp营销",
    "更多",
    "关注列表",
    "小满助手",
    "营销跟进",
    "Facebook Lead表单",
    "OKKI Marketing",
    "浏览记录",
}


@dataclass
class CustomerRun:
    index: int
    page: int
    name: str
    open_ref: Optional[str]
    open_ok: bool
    switched_to_profile: bool
    toggled_common_twice: bool
    toggled_other_twice: bool
    errors: List[str]
    detail_url: Optional[str]


def run_ab(*args: str, timeout_sec: int = 20) -> str:
    proc = subprocess.run(AB + list(args), text=True, capture_output=True, timeout=timeout_sec)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout.strip()


def safe_run_ab(*args: str, timeout_sec: int = 20) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(AB + list(args), text=True, capture_output=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout_sec}s: {' '.join(args)}"
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode == 0, out.strip()


def parse_eval_output(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith('"'):
        raw = json.loads(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def eval_js(js: str, timeout_sec: int = 20):
    return parse_eval_output(run_ab("eval", js, timeout_sec=timeout_sec))


def checkpoint(path: Path, page_kind: str = "detail") -> Dict[str, object]:
    stem = path.stem
    return capture_checkpoint(
        path,
        snapshot_path=OUT_DIR / f"{stem}.checkpoint.snapshot_i.txt",
        probe_path=OUT_DIR / f"{stem}.checkpoint.ready.json",
        page_kind=page_kind,  # type: ignore[arg-type]
        timeout_sec=25,
        stable_rounds=2,
        settle_ms=800,
        run_fn=run_ab,
        eval_fn=eval_js,
    )


def wait_ms(ms: int = 700) -> None:
    safe_run_ab("wait", str(ms))


def snapshot_i(path: Path) -> str:
    text = run_ab("snapshot", "-i")
    path.write_text(text, encoding="utf-8")
    return text


def parse_customer_links(snapshot_text: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for line in snapshot_text.splitlines():
        m = re.match(r'^- link "([^"]+)" \[ref=(e\d+)\]$', line.strip())
        if not m:
            continue
        name, ref = m.group(1), m.group(2)
        if name in NAV_LINKS:
            continue
        out.append((name, ref))
    return out


def parse_list_next_ref(snapshot_text: str) -> Optional[str]:
    for line in snapshot_text.splitlines():
        if 'listitem "下一页"' in line:
            m = re.search(r"ref=(e\d+)", line)
            if m:
                return m.group(1)
    return None


def parse_generic_ref(snapshot_text: str, label: str) -> Optional[str]:
    patt = re.compile(rf'^- generic "{re.escape(label)}" \[ref=(e\d+)\]')
    for line in snapshot_text.splitlines():
        m = patt.match(line.strip())
        if m:
            return m.group(1)
    return None


def is_profile_selected(snapshot_text: str) -> bool:
    return 'tab "资料" [selected' in snapshot_text


def current_url() -> str:
    ok, out = safe_run_ab("get", "url")
    return out.strip() if ok else ""


def build_targets(anchor_name: str, list_snap_1: str, list_snap_2: str) -> List[Tuple[int, str]]:
    names1 = [n for n, _ in parse_customer_links(list_snap_1)]
    idx = -1
    anchor_norm = re.sub(r"\s+", "", anchor_name).lower()
    for i, n in enumerate(names1):
        if re.sub(r"\s+", "", n).lower() == anchor_norm:
            idx = i
            break
    if idx == -1:
        # fallback: from top of current page
        post1 = names1[:]
    else:
        post1 = names1[idx + 1 :]

    names2 = [n for n, _ in parse_customer_links(list_snap_2)]

    targets: List[Tuple[int, str]] = []
    for n in post1:
        targets.append((1, n))
        if len(targets) >= 10:
            return targets
    for n in names2:
        targets.append((2, n))
        if len(targets) >= 10:
            return targets
    return targets


def click_customer_from_list(name: str, list_snapshot: str) -> Optional[str]:
    links = dict(parse_customer_links(list_snapshot))
    ref = links.get(name)
    if not ref:
        return None
    ok, _ = safe_run_ab("click", ref)
    if not ok:
        return None
    wait_ms(1000)
    return ref


def toggle_section_twice(detail_snapshot: str, label: str, run_prefix: str, state: Dict[str, bool]) -> str:
    snap = detail_snapshot
    for j in range(2):
        ref = parse_generic_ref(snap, label)
        if not ref:
            state["ok"] = False
            state.setdefault("errors", []).append(f"missing ref for {label} pass{j+1}")
            return snap
        ok, _ = safe_run_ab("click", ref)
        if not ok:
            state["ok"] = False
            state.setdefault("errors", []).append(f"click failed for {label} ref={ref} pass{j+1}")
            return snap
        wait_ms(700)
        snap = snapshot_i(OUT_DIR / f"{run_prefix}-{label}-toggle{j+1}.i.snapshot.txt")
    return snap


def run_one(index: int, page_no: int, name: str, list_snapshot: str, list_url: str) -> Tuple[CustomerRun, str]:
    errors: List[str] = []
    open_ref = click_customer_from_list(name, list_snapshot)
    if not open_ref:
        rec = CustomerRun(
            index=index,
            page=page_no,
            name=name,
            open_ref=None,
            open_ok=False,
            switched_to_profile=False,
            toggled_common_twice=False,
            toggled_other_twice=False,
            errors=["cannot open from list"],
            detail_url=None,
        )
        return rec, list_snapshot

    detail_url = current_url()
    run_prefix = f"06-c{index:02d}"
    detail_snap = snapshot_i(OUT_DIR / f"{run_prefix}-detail-start.i.snapshot.txt")

    switched = False
    if not is_profile_selected(detail_snap):
        z_ref = parse_generic_ref(detail_snap, "资料")
        if z_ref:
            ok, _ = safe_run_ab("click", z_ref)
            if ok:
                wait_ms(800)
                detail_snap = snapshot_i(OUT_DIR / f"{run_prefix}-after-ziliao.i.snapshot.txt")
                switched = True
            else:
                errors.append(f"failed click 资料 ref={z_ref}")
        else:
            errors.append("missing 资料 ref")
    else:
        switched = True

    common_state = {"ok": True, "errors": []}
    detail_snap = toggle_section_twice(detail_snap, "公司常用信息", run_prefix, common_state)
    if not common_state["ok"]:
        errors.extend(common_state["errors"])

    other_state = {"ok": True, "errors": []}
    detail_snap = toggle_section_twice(detail_snap, "公司其他信息", run_prefix, other_state)
    if not other_state["ok"]:
        errors.extend(other_state["errors"])

    # capture one screenshot per customer at end of detail checks
    checkpoint(SHOT_DIR / f"{run_prefix}-detail.png")

    # return to list by opening known list URL (more stable than browser history back)
    ok, out = safe_run_ab("open", list_url)
    if not ok:
        errors.append(f"open_list_failed: {out[:200]}")
    wait_ms(1000)
    list_after = snapshot_i(OUT_DIR / f"{run_prefix}-back-list.i.snapshot.txt")

    rec = CustomerRun(
        index=index,
        page=page_no,
        name=name,
        open_ref=open_ref,
        open_ok=True,
        switched_to_profile=switched,
        toggled_common_twice=common_state["ok"],
        toggled_other_twice=other_state["ok"],
        errors=errors,
        detail_url=detail_url,
    )
    return rec, list_after


def main() -> None:
    # Go to list tab
    run_ab("tab", "t1")
    wait_ms(700)

    list_url_page1 = run_ab("get", "url")
    list1 = snapshot_i(OUT_DIR / "06-page1-start.snapshot.txt")
    next_ref = parse_list_next_ref(list1)
    if not next_ref:
        raise RuntimeError("Cannot find 下一页 ref on page1")

    # Probe page2 names and go back to page1 baseline
    ok, _ = safe_run_ab("click", next_ref)
    if not ok:
        raise RuntimeError("Cannot navigate to page2 for target planning")
    wait_ms(900)
    list_url_page2 = run_ab("get", "url")
    list2 = snapshot_i(OUT_DIR / "06-page2-probe.snapshot.txt")

    # Return to page1 for ordered processing via deterministic URL open
    ok, _ = safe_run_ab("open", list_url_page1)
    if not ok:
        raise RuntimeError("Cannot open page1 list URL after page2 probe")
    wait_ms(1000)
    list_current = snapshot_i(OUT_DIR / "06-page1-return.snapshot.txt")

    targets = build_targets("WaleedAlrakide", list1, list2)
    targets = targets[:10]

    (OUT_DIR / "06-targets.json").write_text(
        json.dumps([{"page": p, "name": n} for p, n in targets], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    results: List[CustomerRun] = []
    for i, (page_no, name) in enumerate(targets, start=1):
        list_url = list_url_page1 if page_no == 1 else list_url_page2
        ok, out = safe_run_ab("open", list_url)
        if not ok:
            raise RuntimeError(f"Cannot open list page{page_no}: {out[:200]}")
        wait_ms(1000)
        list_current = snapshot_i(OUT_DIR / f"06-c{i:02d}-list-page{page_no}.i.snapshot.txt")
        rec, list_current = run_one(i, page_no, name, list_current, list_url)
        results.append(rec)

    out_json = OUT_DIR / "06-next-10-readonly-results.json"
    out_json.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    out_md = OUT_DIR / "06-next-10-readonly-summary.md"
    lines = [
        "# 06 Next 10 Customers Read-Only Verification",
        "",
        "## Scope",
        "- Open next 10 customers from list order after `WaleedAlrakide`.",
        "- For each customer: ensure `资料` tab context and toggle `公司常用信息`/`公司其他信息` twice.",
        "- No write actions executed (no 编辑/保存/提交/发送/删除/合并/归档).",
        "",
        "## Targets",
    ]
    for t in targets:
        lines.append(f"- page {t[0]}: {t[1]}")
    lines.append("")
    lines.append("## Results")
    for r in results:
        status = "OK" if (r.open_ok and not r.errors and r.switched_to_profile and r.toggled_common_twice and r.toggled_other_twice) else "PARTIAL"
        lines.append(
            f"- #{r.index} {r.name}: {status} | open_ref={r.open_ref} | switched={r.switched_to_profile} | common2={r.toggled_common_twice} | other2={r.toggled_other_twice}"
        )
        if r.errors:
            for e in r.errors:
                lines.append(f"  - error: {e}")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("- logs/recon/06-targets.json")
    lines.append("- logs/recon/06-next-10-readonly-results.json")
    lines.append("- screenshots/recon/06-cXX-detail.png")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(str(out_json))
    print(str(out_md))


if __name__ == "__main__":
    main()
