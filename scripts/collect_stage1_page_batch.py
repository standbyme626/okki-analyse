#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from okki_agent.edge_bridge import _run
from okki_agent.list_page import (
    collect_list_page_rows_via_api,
    get_list_page_state,
)


CSV_FIELDS = [
    "customer_index",
    "page",
    "page_row_index",
    "customer_name",
    "customer_url",
    "country",
    "last_contact",
    "note",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect multiple OKKI list pages with pacing and health checks."
    )
    parser.add_argument("--start-page", type=int, default=0, help="Logical start page; 0 means auto-detect from current list page.")
    parser.add_argument("--pages", type=int, default=10)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--min-raw-count", type=int, default=95)
    parser.add_argument("--page-delay-min", type=float, default=2.0)
    parser.add_argument("--page-delay-max", type=float, default=5.0)
    parser.add_argument("--nav-delay-min", type=float, default=3.0)
    parser.add_argument("--nav-delay-max", type=float, default=6.0)
    parser.add_argument("--extra-break-every", type=int, default=3)
    parser.add_argument("--extra-break-min", type=float, default=10.0)
    parser.add_argument("--extra-break-max", type=float, default=20.0)
    parser.add_argument("--health-snapshot-every", type=int, default=50)
    parser.add_argument("--out", default="", help="Combined CSV output path.")
    parser.add_argument("--raw-dir", default="logs/recon/stage1_batch")
    parser.add_argument("--summary-out", default="")
    parser.add_argument("--progress-out", default="", help="Per-page progress JSONL path.")
    return parser.parse_args()


def sleep_random(min_sec: float, max_sec: float, reason: str, events: List[Dict[str, Any]]) -> None:
    duration = round(random.uniform(min_sec, max_sec), 2)
    events.append({"event": "sleep", "reason": reason, "seconds": duration})
    time.sleep(duration)


def validate_page(
    expected_page: int,
    page_size: int,
    min_raw_count: int,
    api_total_item: int | None,
    expected_total_pages: int | None,
    state: Dict[str, Any],
    result: Dict[str, Any],
) -> List[str]:
    errors: List[str] = []
    if state.get("page_size_text") != f"{page_size} 条/页":
        errors.append(f"page size mismatch: expected {page_size} 条/页, got {state.get('page_size_text')}")
    if not state.get("scroller_found"):
        errors.append("list scroller missing")
    if result.get("page") != expected_page:
        errors.append(f"result page mismatch: expected {expected_page}, got {result.get('page')}")
    if result.get("api_code") not in (0, None):
        errors.append(f"api_code not successful: {result.get('api_code')}")
    raw_count = int(result.get("raw_count") or 0)
    current_api_total_item = result.get("api_total_item")
    if current_api_total_item is not None:
        current_api_total_item = int(current_api_total_item)
    effective_api_total_item = current_api_total_item or api_total_item
    effective_total_pages = expected_total_pages
    if effective_api_total_item:
        effective_total_pages = math.ceil(effective_api_total_item / page_size)
    if (
        effective_api_total_item
        and effective_total_pages
        and expected_page == effective_total_pages
    ):
        expected_final_raw = effective_api_total_item - page_size * (effective_total_pages - 1)
        expected_final_raw = max(1, expected_final_raw)
        if raw_count != expected_final_raw:
            errors.append(
                f"last page raw_count mismatch: expected {expected_final_raw}, got {raw_count}"
            )
    elif raw_count < min_raw_count:
        errors.append(f"raw_count too low: {raw_count} < {min_raw_count}")
    company_ids = [row["company_id"] for row in result.get("rows", [])]
    if len(company_ids) != len(set(company_ids)):
        errors.append("duplicate company_id detected in raw rows")
    blank_country = sum(1 for row in result.get("valid_rows", []) if not row.get("country"))
    if blank_country > 20:
        errors.append(f"too many blank country values: {blank_country}")
    return errors


def write_combined_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            writer.writerow(
                {
                    "customer_index": index,
                    "page": row["page"],
                    "page_row_index": row["page_row_index"],
                    "customer_name": row["customer_name"],
                    "customer_url": row["customer_url"],
                    "country": row.get("country", ""),
                    "last_contact": row.get("last_contact", ""),
                    "note": row["note"],
                }
            )


def append_experiment_log(summary: Dict[str, Any], start_state: Dict[str, Any]) -> None:
    out = Path("logs/experiment-runs.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    completed = summary["completed_pages"]
    requested = summary["requested_pages"]
    status = "success" if completed == requested else ("partial" if completed else "failed")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    record = {
        "timestamp_start": now,
        "timestamp_end": now,
        "objective": "Stage 1 collect OKKI customer list URLs via read-only companyList API",
        "start_url": start_state.get("location", ""),
        "page_mode": "full_page",
        "commands_executed": [
            "python3 scripts/collect_stage1_page_batch.py",
        ],
        "clicked_targets": [],
        "expected_result": f"Collect {requested} logical list pages with health checks and no OKKI writes",
        "actual_result": (
            f"completed_pages={completed}, total_valid_rows={summary['total_valid_rows']}, "
            f"combined_csv={summary['combined_csv']}"
        ),
        "result": status,
        "write_action": {
            "attempted": False,
            "dry_run": True,
            "customer_name": "",
            "old_level": "",
            "new_level": "",
            "old_tags": [],
            "proposed_tags": [],
            "applied_tags": [],
        },
        "screenshot_paths": [summary["final_snapshot"]],
        "artifacts": [
            summary["combined_csv"],
            summary["summary_path"],
            summary["raw_dir"],
        ],
        "conclusion": "Read-only list collection finished" if status == "success" else "Read-only list collection stopped by health check",
    }
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_progress(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    raw_dir = Path(args.raw_dir) / stamp
    raw_dir.mkdir(parents=True, exist_ok=True)

    start_state = get_list_page_state()
    start_page = args.start_page or int(start_state.get("current_page") or 0)
    if start_page <= 0:
        raise RuntimeError(f"Cannot determine current page: {start_state}")

    end_page = start_page + args.pages - 1
    combined_path = Path(args.out) if args.out else Path(
        f"data/stage1_pages{start_page:03d}-{end_page:03d}_urls_{stamp}.csv"
    )
    summary_path = Path(args.summary_out) if args.summary_out else Path(
        f"logs/recon/stage1_pages{start_page:03d}-{end_page:03d}_summary_{stamp}.json"
    )
    progress_path = Path(args.progress_out) if args.progress_out else raw_dir / "page_progress.jsonl"

    events: List[Dict[str, Any]] = []
    all_valid_rows: List[Dict[str, Any]] = []
    page_summaries: List[Dict[str, Any]] = []
    initial_api_total_item: int | None = None
    api_total_item: int | None = None
    expected_total_pages: int | None = None

    for offset in range(args.pages):
        expected_page = start_page + offset
        state = get_list_page_state()
        settle_sec = round(random.uniform(0.35, 0.8), 2)
        result = collect_list_page_rows_via_api(
            page=expected_page,
            expected_page_size=args.page_size,
        )
        events.append({"event": "api_page_request", "page": expected_page, "settle_sec": settle_sec})
        if result.get("api_total_item") is not None:
            current_api_total_item = int(result["api_total_item"])
            if initial_api_total_item is None:
                initial_api_total_item = current_api_total_item
            api_total_item = current_api_total_item
            expected_total_pages = math.ceil(api_total_item / args.page_size)
        errors = validate_page(
            expected_page,
            args.page_size,
            args.min_raw_count,
            api_total_item,
            expected_total_pages,
            state,
            result,
        )

        page_raw_path = raw_dir / f"page{expected_page:03d}.raw.json"
        page_raw_path.write_text(
            json.dumps({"state": state, "result": result, "errors": errors}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

        page_summary = {
            "page": expected_page,
            "state": state,
            "raw_count": result["raw_count"],
            "demo_count": result["demo_count"],
            "valid_count": result["valid_count"],
            "blank_country_count": sum(1 for row in result["valid_rows"] if not row.get("country")),
            "errors": errors,
            "raw_path": str(page_raw_path),
            "api_total_item": result.get("api_total_item"),
            "expected_total_pages": expected_total_pages,
        }
        page_summaries.append(page_summary)
        events.append({"event": "page_collected", **page_summary})
        append_progress(
            progress_path,
            {
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                "page": expected_page,
                "raw_count": result["raw_count"],
                "demo_count": result["demo_count"],
                "valid_count": result["valid_count"],
                "blank_country_count": page_summary["blank_country_count"],
                "errors": errors,
                "combined_csv": str(combined_path),
                "api_total_item": result.get("api_total_item"),
                "expected_total_pages": expected_total_pages,
                "total_valid_rows_so_far": len(all_valid_rows) + (0 if errors else result["valid_count"]),
            },
        )

        if errors:
            snapshot_path = raw_dir / f"page{expected_page:03d}.on-error.snapshot_i.txt"
            snapshot_path.write_text(_run("snapshot", "-i", timeout_sec=20) + "\n", encoding="utf-8")
            page_summary["snapshot_path"] = str(snapshot_path)
            write_combined_csv(combined_path, all_valid_rows)
            break

        all_valid_rows.extend(result["valid_rows"])
        write_combined_csv(combined_path, all_valid_rows)

        if offset == args.pages - 1:
            break

        if args.health_snapshot_every and (offset + 1) % args.health_snapshot_every == 0:
            health_snapshot = raw_dir / f"page{expected_page:03d}.health.snapshot_i.txt"
            health_snapshot.write_text(_run("snapshot", "-i", timeout_sec=20) + "\n", encoding="utf-8")
            events.append(
                {
                    "event": "health_snapshot",
                    "page": expected_page,
                    "path": str(health_snapshot),
                }
            )

        sleep_random(args.page_delay_min, args.page_delay_max, "post-page api pacing", events)
        sleep_random(args.nav_delay_min, args.nav_delay_max, "between logical pages pacing", events)

        if args.extra_break_every and (offset + 1) % args.extra_break_every == 0:
            sleep_random(args.extra_break_min, args.extra_break_max, "periodic batch break", events)

    final_snapshot = raw_dir / "final.snapshot_i.txt"
    final_snapshot.write_text(_run("snapshot", "-i", timeout_sec=20) + "\n", encoding="utf-8")

    summary = {
        "timestamp": stamp,
        "start_page": start_page,
        "requested_pages": args.pages,
        "initial_api_total_item": initial_api_total_item,
        "api_total_item": api_total_item,
        "expected_total_pages": expected_total_pages,
        "completed_pages": len([p for p in page_summaries if not p["errors"]]),
        "combined_csv": str(combined_path),
        "summary_path": str(summary_path),
        "raw_dir": str(raw_dir),
        "progress_path": str(progress_path),
        "final_snapshot": str(final_snapshot),
        "total_valid_rows": len(all_valid_rows),
        "page_summaries": page_summaries,
        "events": events,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    append_experiment_log(summary, start_state)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["completed_pages"] == args.pages else 1


if __name__ == "__main__":
    raise SystemExit(main())
