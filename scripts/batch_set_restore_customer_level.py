#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from okki_agent import writer


INPUT_JSONL = ROOT / "logs" / "profile_field_batch_read.jsonl"
SET_OUT = ROOT / "logs" / "batch_level_set_b.jsonl"
RESTORE_OUT = ROOT / "logs" / "batch_level_restore.jsonl"
SUMMARY_OUT = ROOT / "logs" / "batch_level_roundtrip_summary.md"
SHOT_DIR = ROOT / "screenshots" / "recon" / "batch_level"

TARGET_LEVEL = "B"
WAIT_MS = 10000
OPEN_RETRY = 3
ACTION_RETRY = 3
READY_WAIT_ROUNDS = 20


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def norm(v: Optional[str]) -> str:
    return (v or "").replace("：", ":").replace("\u200b", "").strip()


def is_empty(v: Optional[str]) -> bool:
    return writer.is_empty_like_value(v)


def shot(name: str) -> str:
    path = SHOT_DIR / name
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    writer._ab_run("screenshot", str(path), timeout_sec=20)
    return str(path)


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


@dataclass
class Row:
    customer_index: int
    customer_name: str
    customer_url: str


def load_rows(path: Path) -> List[Row]:
    rows: List[Row] = []
    seen: set[int] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            idx = int(obj.get("customer_index") or 0)
            if idx <= 0 or idx in seen:
                continue
            seen.add(idx)
            rows.append(
                Row(
                    customer_index=idx,
                    customer_name=str(obj.get("customer_name") or ""),
                    customer_url=str(obj.get("customer_url") or ""),
                )
            )
    rows.sort(key=lambda r: r.customer_index)
    return rows


def open_with_retry(url: str, retries: int = OPEN_RETRY) -> str:
    last_err = ""
    for i in range(1, retries + 1):
        try:
            writer._ab_run("open", url, timeout_sec=35)
            writer.wait_ms(WAIT_MS)
            ok, probe = wait_page_ready()
            if ok:
                return f"OPEN_OK:{i}"
            last_err = f"NOT_READY:{probe}"
        except Exception as e:  # pragma: no cover
            last_err = str(e)
            try:
                writer.wait_ms(WAIT_MS)
            except Exception:
                pass
    return f"OPEN_FAIL:{last_err}"


def page_probe() -> Dict[str, Any]:
    title = ""
    url = ""
    try:
        title = writer._ab_run("get", "title", timeout_sec=8)
    except Exception:
        pass
    try:
        url = writer._ab_run("get", "url", timeout_sec=8)
    except Exception:
        pass
    snap_i = ""
    try:
        snap_i = writer._ab_run("snapshot", "-i", timeout_sec=10)
    except Exception:
        pass
    return {
        "title": title,
        "url": url,
        "has_profile_tab": ('tab "资料"' in snap_i) or ("资料" in snap_i),
        "has_edit_btn": ("name=编辑" in snap_i) or ("编辑" in snap_i),
        "has_detail_sections": ("公司常用信息" in snap_i) or ("公司其他信息" in snap_i),
    }


def wait_page_ready(rounds: int = READY_WAIT_ROUNDS) -> tuple[bool, Dict[str, Any]]:
    last: Dict[str, Any] = {}
    for _ in range(rounds):
        probe = page_probe()
        last = probe
        title = probe.get("title") or ""
        url = probe.get("url") or ""
        if ("客户详情" in title or "/crm/customer/personal" in url) and (
            probe.get("has_profile_tab")
            or probe.get("has_edit_btn")
            or probe.get("has_detail_sections")
        ):
            return True, probe
        writer.wait_ms(1000)
    return False, last


def is_edit_mode() -> bool:
    js = """(() => {
      const norm=s=>(s||'').replace(/\\s+/g,'').trim();
      const txt=document.body ? (document.body.innerText||'') : '';
      if(!txt) return false;
      const hasTitle = txt.includes('编辑客户');
      const hasConfirm = [...document.querySelectorAll('button')]
        .some(b=>{const t=norm(b.innerText||b.textContent||''); return t==='确定'||t==='确 定';});
      return !!(hasTitle && hasConfirm);
    })()"""
    try:
        return bool(writer._ab_eval(js, timeout_sec=10))
    except Exception:
        return False


def enter_edit_with_retry(actions: List[Dict[str, Any]]) -> bool:
    for attempt in range(1, ACTION_RETRY + 1):
        out = writer.enter_edit_mode()
        actions.append({"enter_edit_attempt": attempt, "result": out})
        writer.wait_ms(WAIT_MS)
        if out == "CLICK_TOP_EDIT" and is_edit_mode():
            return True
        if out == "NO_TOP_EDIT" and is_edit_mode():
            actions.append({"enter_edit_mode": "ALREADY_EDIT"})
            return True
        writer.wait_ms(1000)
    return False


def set_level_b_with_retry(actions: List[Dict[str, Any]]) -> str:
    last = "SET_B_FAILED"
    for attempt in range(1, ACTION_RETRY + 1):
        sel = writer.select_option_by_text("客户等级", TARGET_LEVEL)
        actions.append({"select_B_attempt": attempt, "result": sel})
        writer.wait_ms(1500)
        last = sel
        if sel.startswith("SET_OPTION:"):
            return sel
        # Retry path: keep edit mode and try again.
        writer.wait_ms(1000)
    return last


def restore_level_with_retry(
    baseline_level: Optional[str],
    actions: List[Dict[str, Any]],
) -> str:
    last = "RESTORE_FAILED"
    for attempt in range(1, ACTION_RETRY + 1):
        if is_empty(baseline_level):
            act = writer.clear_select_field_to_empty("客户等级")
            actions.append({"restore_empty_attempt": attempt, "result": act})
        else:
            act = writer.select_option_by_text("客户等级", str(baseline_level))
            actions.append({"restore_to_baseline_attempt": attempt, "result": act})
        writer.wait_ms(1500)
        last = act
        if act.startswith("SET_OPTION:") or act.startswith("CLEARED_") or act.startswith("ALREADY_EMPTY:"):
            return act
        writer.wait_ms(1000)
    return last


def set_level_to_b(row: Row) -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "timestamp": now_iso(),
        "phase": "set_b",
        "customer_index": row.customer_index,
        "customer_name": row.customer_name,
        "customer_url": row.customer_url,
        "status": "error",
        "error": None,
        "baseline_level": None,
        "after_level": None,
        "actions": [],
        "screenshots": [],
    }
    try:
        op = open_with_retry(row.customer_url)
        rec["actions"].append({"open": op})
        if not op.startswith("OPEN_OK"):
            rec["error"] = op
            return rec

        rec["screenshots"].append(shot(f"idx{row.customer_index:03d}-set-before.png"))
        before = writer.read_visible_field_value("客户等级")
        rec["baseline_level"] = before
        rec["actions"].append({"read_before": before})

        if norm(before) == TARGET_LEVEL:
            rec["after_level"] = before
            rec["status"] = "success"
            rec["actions"].append({"skip": "ALREADY_B"})
            return rec

        if not enter_edit_with_retry(rec["actions"]):
            rec["error"] = "enter_edit_failed_after_retries"
            return rec
        rec["actions"].append({"expand_common": writer.expand_common_info()})
        rec["actions"].append({"wait_expand": writer.wait_ms(WAIT_MS)})

        sel = set_level_b_with_retry(rec["actions"])
        rec["actions"].append({"select_B_final": sel})
        rec["actions"].append({"wait_after_select": writer.wait_ms(WAIT_MS)})
        rec["screenshots"].append(shot(f"idx{row.customer_index:03d}-set-before-save.png"))

        save_out = writer.save_changes()
        rec["actions"].append({"save": save_out})
        if save_out == "NO_CONFIRM":
            rec["error"] = "save_no_confirm"
            return rec
        rec["actions"].append({"wait_after_save": writer.wait_ms(WAIT_MS)})

        after = writer.read_visible_field_value("客户等级")
        rec["after_level"] = after
        rec["actions"].append({"read_after": after})
        rec["screenshots"].append(shot(f"idx{row.customer_index:03d}-set-after-save.png"))

        if norm(after) == TARGET_LEVEL:
            rec["status"] = "success"
        else:
            rec["status"] = "error"
            rec["error"] = f"verify_failed_after_set: expected={TARGET_LEVEL}, got={after}"
    except Exception as e:  # pragma: no cover
        rec["error"] = str(e)
        try:
            rec["screenshots"].append(shot(f"idx{row.customer_index:03d}-set-on-error.png"))
        except Exception:
            pass
    return rec


def restore_level(row: Row, baseline_level: Optional[str]) -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "timestamp": now_iso(),
        "phase": "restore",
        "customer_index": row.customer_index,
        "customer_name": row.customer_name,
        "customer_url": row.customer_url,
        "status": "error",
        "error": None,
        "baseline_level": baseline_level,
        "before_restore_level": None,
        "after_restore_level": None,
        "actions": [],
        "screenshots": [],
    }
    try:
        op = open_with_retry(row.customer_url)
        rec["actions"].append({"open": op})
        if not op.startswith("OPEN_OK"):
            rec["error"] = op
            return rec

        rec["screenshots"].append(shot(f"idx{row.customer_index:03d}-restore-before.png"))
        before = writer.read_visible_field_value("客户等级")
        rec["before_restore_level"] = before
        rec["actions"].append({"read_before_restore": before})

        if not enter_edit_with_retry(rec["actions"]):
            rec["error"] = "enter_edit_failed_after_retries"
            return rec
        rec["actions"].append({"expand_common": writer.expand_common_info()})
        rec["actions"].append({"wait_expand": writer.wait_ms(WAIT_MS)})

        act = restore_level_with_retry(baseline_level, rec["actions"])
        rec["actions"].append({"restore_final": act})

        rec["actions"].append({"wait_after_restore_select": writer.wait_ms(WAIT_MS)})
        rec["screenshots"].append(shot(f"idx{row.customer_index:03d}-restore-before-save.png"))

        save_out = writer.save_changes()
        rec["actions"].append({"save": save_out})
        if save_out == "NO_CONFIRM":
            rec["error"] = "save_no_confirm"
            return rec
        rec["actions"].append({"wait_after_save": writer.wait_ms(WAIT_MS)})

        after = writer.read_visible_field_value("客户等级")
        rec["after_restore_level"] = after
        rec["actions"].append({"read_after_restore": after})
        rec["screenshots"].append(shot(f"idx{row.customer_index:03d}-restore-after-save.png"))

        if is_empty(baseline_level):
            ok = is_empty(after)
        else:
            ok = norm(after) == norm(str(baseline_level))
        if ok:
            rec["status"] = "success"
        else:
            rec["status"] = "error"
            rec["error"] = f"verify_failed_after_restore: baseline={baseline_level}, got={after}"
    except Exception as e:  # pragma: no cover
        rec["error"] = str(e)
        try:
            rec["screenshots"].append(shot(f"idx{row.customer_index:03d}-restore-on-error.png"))
        except Exception:
            pass
    return rec


def main() -> int:
    rows = load_rows(INPUT_JSONL)
    if not rows:
        print("no rows in input")
        return 1

    # never touch input file; only create separate outputs
    SET_OUT.write_text("", encoding="utf-8")
    RESTORE_OUT.write_text("", encoding="utf-8")

    set_results: List[Dict[str, Any]] = []
    baseline_by_idx: Dict[int, Optional[str]] = {}

    for i, row in enumerate(rows, start=1):
        rec = set_level_to_b(row)
        append_jsonl(SET_OUT, rec)
        set_results.append(rec)
        baseline_by_idx[row.customer_index] = rec.get("baseline_level")
        if i % 5 == 0:
            print(f"set_b progress: {i}/{len(rows)}", flush=True)

    restore_results: List[Dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        rec = restore_level(row, baseline_by_idx.get(row.customer_index))
        append_jsonl(RESTORE_OUT, rec)
        restore_results.append(rec)
        if i % 5 == 0:
            print(f"restore progress: {i}/{len(rows)}", flush=True)

    set_ok = sum(1 for r in set_results if r.get("status") == "success")
    restore_ok = sum(1 for r in restore_results if r.get("status") == "success")
    set_fail = [r for r in set_results if r.get("status") != "success"]
    restore_fail = [r for r in restore_results if r.get("status") != "success"]

    lines: List[str] = []
    lines.append("# Batch Level Roundtrip Summary")
    lines.append("")
    lines.append(f"- total_customers: {len(rows)}")
    lines.append(f"- set_to_B_success: {set_ok}")
    lines.append(f"- set_to_B_failed: {len(set_fail)}")
    lines.append(f"- restore_success: {restore_ok}")
    lines.append(f"- restore_failed: {len(restore_fail)}")
    lines.append("")
    if set_fail:
        lines.append("## Set-B Failed Indexes")
        for r in set_fail:
            lines.append(f"- idx={r.get('customer_index')}, error={r.get('error')}")
        lines.append("")
    if restore_fail:
        lines.append("## Restore Failed Indexes")
        for r in restore_fail:
            lines.append(f"- idx={r.get('customer_index')}, error={r.get('error')}")
        lines.append("")
    lines.append("## Output Files")
    lines.append(f"- set log: `{SET_OUT}`")
    lines.append(f"- restore log: `{RESTORE_OUT}`")
    lines.append("")
    lines.append("## Statement")
    lines.append("- only field modified: `客户等级`")
    lines.append("- baseline came from live read before set")
    lines.append("- restore used per-customer baseline")
    SUMMARY_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "total": len(rows),
                "set_ok": set_ok,
                "set_fail": len(set_fail),
                "restore_ok": restore_ok,
                "restore_fail": len(restore_fail),
                "set_log": str(SET_OUT),
                "restore_log": str(RESTORE_OUT),
                "summary": str(SUMMARY_OUT),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
