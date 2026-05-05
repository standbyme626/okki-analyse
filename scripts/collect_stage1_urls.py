#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from okki_agent.edge_bridge import _run
from okki_agent.list_page import collect_list_page_rows_via_api, get_list_page_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect one OKKI list-page customer URL page without writes."
    )
    parser.add_argument("--page", type=int, default=0, help="Expected page number; 0 means auto-detect.")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--out", default="", help="CSV output path. Defaults to data/stage1_page{page}_urls_<ts>.csv")
    parser.add_argument("--raw-out", default="", help="Raw JSON output path.")
    parser.add_argument("--summary-out", default="", help="Summary JSON output path.")
    parser.add_argument("--snapshot-out", default="", help="Final snapshot -i path.")
    parser.add_argument("--limit", type=int, default=0, help="Limit output rows after demo filtering; 0 means all.")
    return parser.parse_args()


def default_paths(page: int, stamp: str) -> Dict[str, Path]:
    return {
        "csv": Path(f"data/stage1_page{page}_urls_{stamp}.csv"),
        "raw": Path(f"logs/recon/stage1_page{page}_urls_{stamp}.raw.json"),
        "summary": Path(f"logs/recon/stage1_page{page}_urls_{stamp}.summary.json"),
        "snapshot": Path(f"logs/recon/stage1_page{page}_urls_{stamp}.snapshot_i.txt"),
    }


def write_existing_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "customer_index",
                "customer_name",
                "customer_url",
                "country",
                "last_contact",
                "note",
            ],
        )
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            writer.writerow(
                {
                    "customer_index": index,
                    "customer_name": row["customer_name"],
                    "customer_url": row["customer_url"],
                    "country": row.get("country", ""),
                    "last_contact": row.get("last_contact", ""),
                    "note": row["note"],
                }
            )


def main() -> int:
    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    state = get_list_page_state()
    page = args.page or int(state.get("current_page") or 0)
    if page <= 0:
        raise RuntimeError(f"Cannot determine current list page: {state}")

    paths = default_paths(page, stamp)
    csv_path = Path(args.out) if args.out else paths["csv"]
    raw_path = Path(args.raw_out) if args.raw_out else paths["raw"]
    summary_path = Path(args.summary_out) if args.summary_out else paths["summary"]
    snapshot_path = Path(args.snapshot_out) if args.snapshot_out else paths["snapshot"]

    result = collect_list_page_rows_via_api(page=page, expected_page_size=args.page_size)
    valid_rows = result["valid_rows"]
    output_rows = valid_rows[: args.limit] if args.limit else valid_rows

    write_existing_csv(csv_path, output_rows)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps(
            {
                "timestamp": stamp,
                "list_state": state,
                **result,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(_run("snapshot", "-i", timeout_sec=20) + "\n", encoding="utf-8")

    summary = {
        "timestamp": stamp,
        "page": page,
        "list_state": state,
        "csv_path": str(csv_path),
        "raw_path": str(raw_path),
        "summary_path": str(summary_path),
        "snapshot_path": str(snapshot_path),
        "raw_count": result["raw_count"],
        "demo_count": result["demo_count"],
        "valid_count": result["valid_count"],
        "output_count": len(output_rows),
        "first_5_valid": output_rows[:5],
        "last_5_valid": output_rows[-5:],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
