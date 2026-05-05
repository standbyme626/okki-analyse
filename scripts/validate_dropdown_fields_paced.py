#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from okki_agent import writer


FIELDS = [
    "客户等级",
    "客户销售渠道",
    "客户类型",
    "年采购额",
    "规模",
]

WAIT_OPEN_MS = 5000
WAIT_AFTER_FILL_MS = 5000
WAIT_AFTER_SAVE_MS = 5000


def now_tag() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def shot(path: Path) -> str:
    writer._ab_run("screenshot", str(path))
    return str(path)


def set_first(label: str) -> str:
    if label == "客户等级":
        return writer.set_customer_level_first()
    if label == "客户销售渠道":
        return writer.set_customer_sales_channel_first()
    if label == "客户类型":
        return writer.set_customer_type_first()
    if label == "年采购额":
        return writer.set_annual_procurement_first()
    if label == "规模":
        return writer.set_scale_first()
    return f"UNSUPPORTED:{label}"


def run_one_field(label: str, ts: str, shot_dir: Path) -> Dict[str, Any]:
    before_value = writer.read_visible_field_value(label)
    rec: Dict[str, Any] = {
        "field": label,
        "before": before_value,
        "write_policy": "only_modify_when_empty",
        "set_phase": {},
        "restore_phase": {},
        "restored_to_empty": False,
    }
    if not writer.is_empty_like_value(before_value):
        rec["set_phase"] = {
            "skipped": True,
            "reason": "SKIPPED_HAS_VALUE",
            "before_value": before_value,
        }
        rec["restore_phase"] = {
            "skipped": True,
            "reason": "SKIPPED_HAS_VALUE",
            "before_value": before_value,
            "after_skip": writer.read_visible_field_value(label),
        }
        rec["restored_to_empty"] = True
        rec["skipped_non_empty"] = True
        return rec

    # set phase
    rec["set_phase"]["enter_edit"] = writer.enter_edit_mode()
    rec["set_phase"]["wait_open"] = writer.wait_ms(WAIT_OPEN_MS)
    rec["set_phase"]["expand_common"] = writer.expand_common_info()
    rec["set_phase"]["wait_expand"] = writer.wait_ms(WAIT_OPEN_MS)
    rec["set_phase"]["set_first"] = set_first(label)
    rec["set_phase"]["wait_after_fill"] = writer.wait_ms(WAIT_AFTER_FILL_MS)
    rec["set_phase"]["shot_before_save"] = shot(shot_dir / f"{ts}-{label}-set-before-save.png")
    rec["set_phase"]["save"] = writer.save_changes()
    rec["set_phase"]["wait_after_save"] = writer.wait_ms(WAIT_AFTER_SAVE_MS)
    rec["set_phase"]["after_set"] = writer.read_visible_field_value(label)
    rec["set_phase"]["shot_after_save"] = shot(shot_dir / f"{ts}-{label}-set-after-save.png")

    # restore to empty phase
    rec["restore_phase"]["enter_edit"] = writer.enter_edit_mode()
    rec["restore_phase"]["wait_open"] = writer.wait_ms(WAIT_OPEN_MS)
    rec["restore_phase"]["expand_common"] = writer.expand_common_info()
    rec["restore_phase"]["wait_expand"] = writer.wait_ms(WAIT_OPEN_MS)
    rec["restore_phase"]["clear_to_empty"] = writer.clear_select_field_to_empty(label)
    rec["restore_phase"]["wait_after_fill"] = writer.wait_ms(WAIT_AFTER_FILL_MS)
    rec["restore_phase"]["shot_before_save"] = shot(shot_dir / f"{ts}-{label}-clear-before-save.png")
    rec["restore_phase"]["save"] = writer.save_changes()
    rec["restore_phase"]["wait_after_save"] = writer.wait_ms(WAIT_AFTER_SAVE_MS)
    rec["restore_phase"]["after_clear"] = writer.read_visible_field_value(label)
    rec["restore_phase"]["shot_after_save"] = shot(shot_dir / f"{ts}-{label}-clear-after-save.png")

    after_clear = rec["restore_phase"]["after_clear"]
    rec["restored_to_empty"] = after_clear in {"--", "", None}
    rec["skipped_non_empty"] = False
    return rec


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    log_dir = root / "logs" / "recon"
    shot_dir = root / "screenshots" / "recon"
    log_dir.mkdir(parents=True, exist_ok=True)
    shot_dir.mkdir(parents=True, exist_ok=True)
    ts = now_tag()

    report: Dict[str, Any] = {
        "objective": "Validate dropdown write/restore with paced 5s waits",
        "start_url": writer._ab_run("get", "url"),
        "timestamp": ts,
        "wait_policy_ms": {
            "open": WAIT_OPEN_MS,
            "after_fill": WAIT_AFTER_FILL_MS,
            "after_save": WAIT_AFTER_SAVE_MS,
        },
        "fields": [],
        "success_count": 0,
        "total": len(FIELDS),
    }

    report["global_before_shot"] = shot(shot_dir / f"{ts}-global-before.png")

    for label in FIELDS:
        try:
            field_result = run_one_field(label, ts, shot_dir)
            report["fields"].append(field_result)
            if field_result.get("restored_to_empty"):
                report["success_count"] += 1
        except Exception as exc:  # pragma: no cover
            report["fields"].append(
                {
                    "field": label,
                    "error": str(exc),
                    "restored_to_empty": False,
                }
            )

    report["global_after_shot"] = shot(shot_dir / f"{ts}-global-after.png")
    out = log_dir / f"validate-dropdown-paced-{ts}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))
    print(
        json.dumps(
            {"success_count": report["success_count"], "total": report["total"]},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
