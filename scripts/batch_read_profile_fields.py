#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from okki_agent.edge_bridge import capture_checkpoint
from okki_agent.page_model import (
    detect_page_mode,
    detect_profile_tab_state,
    detect_section_state,
)
from okki_agent.reader import (
    read_common_info_fields,
    read_current_customer_profile,
    read_other_info_fields,
)


AB = ["agent-browser", "--session", "okki"]
CSV_PATH = Path("data/readonly_customer_sample.csv")
OUT_JSONL = Path("logs/profile_field_batch_read.jsonl")
OUT_REPORT = Path("logs/profile_field_completeness_report.md")
ARTIFACT_DIR = Path("logs/recon/batch_read")
SHOT_DIR = Path("screenshots/recon/batch_read")
PRE_WAIT_MS = 10_000
POST_SCROLL_WAIT_MS = 10_000
SCROLL_PX = 420


@dataclass
class InputRow:
    customer_index: int
    customer_name: str
    customer_url: str
    note: str


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_ab(*args: str, timeout_sec: int = 20) -> str:
    p = subprocess.run(AB + list(args), text=True, capture_output=True, timeout=timeout_sec)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip())
    return (p.stdout or "").strip()


def safe_ab(*args: str, timeout_sec: int = 20) -> Tuple[bool, str]:
    try:
        p = subprocess.run(AB + list(args), text=True, capture_output=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout_sec}s: {' '.join(args)}"
    out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    return p.returncode == 0, out.strip()


def parse_eval_output(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith('"'):
        raw = json.loads(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def eval_js(js: str, timeout_sec: int = 20) -> Any:
    return parse_eval_output(run_ab("eval", js, timeout_sec=timeout_sec))


def checkpoint(path: Path, page_kind: str = "detail") -> Dict[str, Any]:
    stem = path.stem
    return capture_checkpoint(
        path,
        snapshot_path=ARTIFACT_DIR / f"{stem}.checkpoint.snapshot_i.txt",
        probe_path=ARTIFACT_DIR / f"{stem}.checkpoint.ready.json",
        page_kind=page_kind,  # type: ignore[arg-type]
        timeout_sec=25,
        stable_rounds=2,
        settle_ms=800,
        run_fn=run_ab,
        eval_fn=eval_js,
    )


def wait_detail_loaded(max_wait_sec: int = 10) -> Tuple[bool, str, str, str, str]:
    """Wait up to max_wait_sec for detail page landmarks.

    Returns: (loaded, url, title, snapshot_i, snapshot_full)
    """
    last_url = ""
    last_title = ""
    last_i = ""
    last_full = ""
    for _ in range(max_wait_sec):
        ok_u, out_u = safe_ab("get", "url", timeout_sec=6)
        ok_t, out_t = safe_ab("get", "title", timeout_sec=6)
        ok_i, out_i = safe_ab("snapshot", "-i", timeout_sec=8)
        ok_f, out_f = safe_ab("snapshot", timeout_sec=8)

        last_url = out_u if ok_u else last_url
        last_title = out_t if ok_t else last_title
        last_i = out_i if ok_i else last_i
        last_full = out_f if ok_f else last_full

        # loaded heuristics: tab/section landmarks or customer detail title
        if (
            ('tab "资料"' in last_i)
            or ("公司常用信息" in last_full and "公司其他信息" in last_full)
            or ("客户详情" in last_title)
        ):
            return True, last_url, last_title, last_i, last_full

        safe_ab("wait", "1000", timeout_sec=4)

    return False, last_url, last_title, last_i, last_full


def passive_delay_and_scroll(record: Dict[str, Any]) -> None:
    """Apply fixed pacing to reduce aggressive request patterns.

    Sequence:
    1) wait 10s after open
    2) scroll down once
    3) wait 10s before extraction / next step
    """
    safe_ab("wait", str(PRE_WAIT_MS), timeout_sec=15)
    record["actions"].append(
        {
            "safe_action": "wait",
            "ms": PRE_WAIT_MS,
            "reason": "fixed pacing before read to reduce anti-bot risk",
        }
    )
    safe_ab("scroll", "down", str(SCROLL_PX), timeout_sec=10)
    record["actions"].append(
        {
            "safe_action": "scroll",
            "direction": "down",
            "px": SCROLL_PX,
            "reason": "light human-like interaction; no write impact",
        }
    )
    safe_ab("wait", str(POST_SCROLL_WAIT_MS), timeout_sec=15)
    record["actions"].append(
        {
            "safe_action": "wait",
            "ms": POST_SCROLL_WAIT_MS,
            "reason": "fixed pacing before moving to extraction/next customer",
        }
    )


def parse_ref(snapshot_i_text: str, label: str) -> Optional[str]:
    # Match lines such as: - generic "资料" [ref=e45] clickable ...
    patt = re.compile(rf'^- generic "{re.escape(label)}" \[ref=(e\d+)\]')
    for ln in snapshot_i_text.splitlines():
        m = patt.match(ln.strip())
        if m:
            return m.group(1)
    return None


def load_rows(csv_path: Path) -> List[InputRow]:
    rows: List[InputRow] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("customer_url") or "").strip()
            if not url:
                continue
            idx = int((row.get("customer_index") or "0").strip() or 0)
            rows.append(
                InputRow(
                    customer_index=idx,
                    customer_name=(row.get("customer_name") or "").strip(),
                    customer_url=url,
                    note=(row.get("note") or "").strip(),
                )
            )
    return rows


def ensure_dirs() -> None:
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)


def write_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def process_one(row: InputRow) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "timestamp": now_iso(),
        "customer_index": row.customer_index,
        "customer_name": row.customer_name,
        "customer_url": row.customer_url,
        "note": row.note,
        "status": "error",
        "page_mode": "unknown",
        "error": None,
        "actions": [],
        "evidence": {"snapshot_files": [], "screenshot_files": [], "checkpoint_meta": []},
    }

    prefix = f"idx{row.customer_index:03d}"
    try:
        run_ab("open", row.customer_url, timeout_sec=20)
        passive_delay_and_scroll(record)
        loaded, current_url, current_title, snap_i, snap_full = wait_detail_loaded(max_wait_sec=10)
        if not loaded:
            record["error"] = "timeout_not_loaded_within_10s"
            record["final_url"] = current_url
            record["title"] = current_title
            record["status"] = "error"
            return record

        snap_i_path = ARTIFACT_DIR / f"{prefix}-initial.snapshot_i.txt"
        snap_full_path = ARTIFACT_DIR / f"{prefix}-initial.snapshot.txt"
        snap_i_path.write_text(snap_i, encoding="utf-8")
        snap_full_path.write_text(snap_full, encoding="utf-8")
        record["evidence"]["snapshot_files"].extend([str(snap_i_path), str(snap_full_path)])

        shot_before = SHOT_DIR / f"{prefix}-before-read.png"
        before_meta = checkpoint(shot_before)
        record["evidence"]["checkpoint_meta"].append(before_meta)
        if before_meta.get("captured") and before_meta.get("screenshot_path"):
            record["evidence"]["screenshot_files"].append(str(before_meta["screenshot_path"]))

        mode_det = detect_page_mode(current_url, current_title, snap_full)
        record["page_mode"] = mode_det.mode.value
        record["mode_reasons"] = mode_det.reasons

        # Ensure on `资料` tab (safe tab navigation only)
        tab_state = detect_profile_tab_state(snap_full)
        if not tab_state.is_profile_selected:
            ref_profile = parse_ref(snap_i, "资料")
            if ref_profile:
                record["actions"].append(
                    {
                        "safe_click": True,
                        "target_ref": ref_profile,
                        "label": "资料",
                        "reason": "switch to profile tab for read-only field extraction",
                    }
                )
                run_ab("click", ref_profile, timeout_sec=10)
                safe_ab("wait", "900", timeout_sec=5)
                snap_i = run_ab("snapshot", "-i", timeout_sec=10)
                snap_full = run_ab("snapshot", timeout_sec=10)
                snap_i_after = ARTIFACT_DIR / f"{prefix}-after-profile-tab.snapshot_i.txt"
                snap_full_after = ARTIFACT_DIR / f"{prefix}-after-profile-tab.snapshot.txt"
                snap_i_after.write_text(snap_i, encoding="utf-8")
                snap_full_after.write_text(snap_full, encoding="utf-8")
                record["evidence"]["snapshot_files"].extend([str(snap_i_after), str(snap_full_after)])
            else:
                record["errors_profile_tab"] = "profile tab ref not found"

        # Expand sections when collapsed only (safe section-toggle only)
        for section_name in ("公司常用信息", "公司其他信息"):
            sec_state = detect_section_state(snap_full, section_name)
            if sec_state.state == "collapsed":
                sec_ref = parse_ref(snap_i, section_name)
                if sec_ref:
                    record["actions"].append(
                        {
                            "safe_click": True,
                            "target_ref": sec_ref,
                            "label": section_name,
                            "reason": "expand section to read fields",
                        }
                    )
                    run_ab("click", sec_ref, timeout_sec=10)
                    safe_ab("wait", "700", timeout_sec=5)
                    snap_i = run_ab("snapshot", "-i", timeout_sec=10)
                    snap_full = run_ab("snapshot", timeout_sec=10)
                    sec_i = ARTIFACT_DIR / f"{prefix}-{section_name}-expanded.snapshot_i.txt"
                    sec_f = ARTIFACT_DIR / f"{prefix}-{section_name}-expanded.snapshot.txt"
                    sec_i.write_text(snap_i, encoding="utf-8")
                    sec_f.write_text(snap_full, encoding="utf-8")
                    record["evidence"]["snapshot_files"].extend([str(sec_i), str(sec_f)])
                else:
                    record.setdefault("section_warnings", []).append(
                        f"section ref not found: {section_name}"
                    )

        common = read_common_info_fields(snap_full)
        other = read_other_info_fields(snap_full)
        unified = read_current_customer_profile(snap_full, current_url, current_title)

        record["final_url"] = current_url
        record["title"] = current_title
        record["common_info"] = common.value if common.ok else {}
        record["other_info"] = other.value if other.ok else {}
        record["profile_schema"] = unified.value if unified.ok else {}
        record["status"] = "success"

        shot_after = SHOT_DIR / f"{prefix}-after-read.png"
        after_meta = checkpoint(shot_after)
        record["evidence"]["checkpoint_meta"].append(after_meta)
        if after_meta.get("captured") and after_meta.get("screenshot_path"):
            record["evidence"]["screenshot_files"].append(str(after_meta["screenshot_path"]))

    except Exception as e:
        record["error"] = str(e)

    return record


def build_completeness_report(jsonl_path: Path, md_path: Path) -> None:
    rows: List[Dict[str, Any]] = []
    if jsonl_path.exists():
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))

    total = len(rows)
    success_rows = [r for r in rows if r.get("status") == "success"]
    failed_rows = [r for r in rows if r.get("status") != "success"]

    field_presence: Counter[str] = Counter()
    field_empty: Counter[str] = Counter()
    extra_field_counter: Counter[str] = Counter()
    missing_field_counter: Counter[str] = Counter()
    mode_counter: Counter[str] = Counter()

    for r in success_rows:
        schema = r.get("profile_schema") or {}
        mode_counter.update([schema.get("page_mode", r.get("page_mode", "unknown"))])

        sections = schema.get("sections") or {}
        for sec_name in ("公司常用信息", "公司其他信息"):
            sec = sections.get(sec_name) or {}
            for k, v in sec.items():
                field_presence[k] += 1
                if v in (None, "", "--"):
                    field_empty[k] += 1

        extra = sections.get("extra_fields") or {}
        for k in extra.keys():
            extra_field_counter[k] += 1

        for k in sections.get("missing_fields") or []:
            missing_field_counter[k] += 1

    stable_fields = []
    unstable_fields = []
    denom = max(len(success_rows), 1)
    for fld, present in sorted(field_presence.items()):
        empty_ratio = field_empty.get(fld, 0) / denom
        if empty_ratio <= 0.2:
            stable_fields.append((fld, present, field_empty.get(fld, 0)))
        else:
            unstable_fields.append((fld, present, field_empty.get(fld, 0)))

    drawer_fullpage_note = ""
    if mode_counter:
        if len(mode_counter) == 1:
            only = next(iter(mode_counter.keys()))
            drawer_fullpage_note = f"本次样本仅出现 `{only}`。"
        else:
            drawer_fullpage_note = f"出现多种模式: {dict(mode_counter)}。"

    lines: List[str] = []
    lines.append("# Profile Field Completeness Report")
    lines.append("")
    lines.append(f"- 总客户数: {total}")
    lines.append(f"- 成功读取数: {len(success_rows)}")
    lines.append(f"- 失败数: {len(failed_rows)}")
    lines.append("")
    lines.append("## 每个字段出现次数")
    for k, c in sorted(field_presence.items()):
        lines.append(f"- {k}: {c}")
    lines.append("")
    lines.append("## 每个字段为空次数")
    for k, c in sorted(field_empty.items()):
        lines.append(f"- {k}: {c}")
    lines.append("")
    lines.append("## extra_fields 汇总")
    if extra_field_counter:
        for k, c in sorted(extra_field_counter.items()):
            lines.append(f"- {k}: {c}")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## missing_fields 汇总")
    if missing_field_counter:
        for k, c in sorted(missing_field_counter.items()):
            lines.append(f"- {k}: {c}")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 哪些字段稳定")
    if stable_fields:
        for k, present, empty_c in stable_fields:
            lines.append(f"- {k}: 出现 {present}, 为空 {empty_c}")
    else:
        lines.append("- 暂无")
    lines.append("")
    lines.append("## 哪些字段不稳定")
    if unstable_fields:
        for k, present, empty_c in unstable_fields:
            lines.append(f"- {k}: 出现 {present}, 为空 {empty_c}")
    else:
        lines.append("- 暂无")
    lines.append("")
    lines.append("## drawer/full_page 差异")
    lines.append(f"- {drawer_fullpage_note or '无足够样本'}")
    lines.append(f"- 模式计数: {dict(mode_counter)}")
    lines.append("")
    lines.append("## 声明")
    lines.append("- 本报告来自批量只读验证；未执行任何写入类动作。")

    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ensure_dirs()
    if not CSV_PATH.exists():
        print(f"CSV not found: {CSV_PATH}")
        return 1

    rows = load_rows(CSV_PATH)
    if not rows:
        print("No customer_url rows found in CSV; template only.")
        OUT_JSONL.write_text("", encoding="utf-8")
        build_completeness_report(OUT_JSONL, OUT_REPORT)
        return 0

    OUT_JSONL.write_text("", encoding="utf-8")

    for i, row in enumerate(rows, start=1):
        rec = process_one(row)
        write_jsonl(OUT_JSONL, rec)
        if i % 10 == 0:
            print(f"progress: {i}/{len(rows)}", flush=True)

    build_completeness_report(OUT_JSONL, OUT_REPORT)
    print(f"done: {OUT_JSONL}")
    print(f"done: {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
