#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Append one OKKI experiment record to logs/experiment-runs.jsonl"
    )
    p.add_argument("--objective", required=True)
    p.add_argument("--start-url", required=True)
    p.add_argument("--page-mode", choices=["drawer", "full_page"], required=True)
    p.add_argument("--expected-result", required=True)
    p.add_argument("--actual-result", required=True)
    p.add_argument("--result", choices=["success", "partial", "failed"], required=True)
    p.add_argument("--command", action="append", default=[], help="Repeatable")
    p.add_argument(
        "--click",
        action="append",
        default=[],
        help="Repeatable: target|target_type|reason (e.g. e91|ref|open first customer)",
    )
    p.add_argument("--screenshot", action="append", default=[], help="Repeatable")
    p.add_argument("--artifact", action="append", default=[], help="Repeatable")
    p.add_argument("--conclusion", default="")
    p.add_argument("--out", default="logs/experiment-runs.jsonl")
    return p.parse_args()


def parse_click(click: str) -> dict:
    parts = click.split("|", 2)
    if len(parts) != 3:
        raise ValueError(
            f"Invalid --click value: {click}. Expected target|target_type|reason"
        )
    target, target_type, reason = parts
    return {"target": target, "target_type": target_type, "reason": reason}


def main() -> None:
    args = parse_args()
    clicks = [parse_click(c) for c in args.click]
    record = {
        "timestamp_start": now_iso(),
        "timestamp_end": now_iso(),
        "objective": args.objective,
        "start_url": args.start_url,
        "page_mode": args.page_mode,
        "commands_executed": args.command,
        "clicked_targets": clicks,
        "expected_result": args.expected_result,
        "actual_result": args.actual_result,
        "result": args.result,
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
        "screenshot_paths": args.screenshot,
        "artifacts": args.artifact,
        "conclusion": args.conclusion,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(str(out))


if __name__ == "__main__":
    main()
