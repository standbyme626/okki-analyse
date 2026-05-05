#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_batch_module():
    mod_path = ROOT / "scripts" / "batch_read_profile_fields.py"
    spec = importlib.util.spec_from_file_location("batch_read_profile_fields", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def find_bad_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows if r.get("status") != "success"]


def retry_one(mod, src_row: Dict[str, Any], retries: int) -> Dict[str, Any]:
    input_row = mod.InputRow(
        customer_index=int(src_row.get("customer_index") or 0),
        customer_name=str(src_row.get("customer_name") or ""),
        customer_url=str(src_row.get("customer_url") or ""),
        note=str(src_row.get("note") or ""),
    )
    last = None
    for attempt in range(1, retries + 1):
        rec = mod.process_one(input_row)
        rec["retry_meta"] = {
            "attempt": attempt,
            "max_attempts": retries,
        }
        last = rec
        if rec.get("status") == "success":
            break
    assert last is not None
    return last


def merge_rows(
    original: List[Dict[str, Any]],
    retry_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    replacement: Dict[int, Dict[str, Any]] = {}
    for r in retry_rows:
        idx = int(r.get("customer_index") or 0)
        replacement[idx] = r

    merged: List[Dict[str, Any]] = []
    for row in original:
        idx = int(row.get("customer_index") or 0)
        merged.append(replacement.get(idx, row))
    return merged, replacement


def main() -> int:
    ap = argparse.ArgumentParser(description="Retry bad records in profile_field_batch_read.jsonl")
    ap.add_argument(
        "--input",
        default="logs/profile_field_batch_read.jsonl",
        help="source JSONL path",
    )
    ap.add_argument(
        "--retry-out",
        default="logs/profile_field_batch_read_retry4.jsonl",
        help="retry-only JSONL output path",
    )
    ap.add_argument(
        "--merged-out",
        default="logs/profile_field_batch_read_refreshed.jsonl",
        help="merged JSONL output path",
    )
    ap.add_argument(
        "--retries",
        type=int,
        default=3,
        help="max retry attempts per bad row",
    )
    args = ap.parse_args()

    src_path = Path(args.input)
    retry_out = Path(args.retry_out)
    merged_out = Path(args.merged_out)

    rows = read_jsonl(src_path)
    if not rows:
        print(json.dumps({"error": f"empty_or_missing_input:{src_path}"}, ensure_ascii=False))
        return 1

    bad = find_bad_rows(rows)
    if not bad:
        write_jsonl(retry_out, [])
        write_jsonl(merged_out, rows)
        print(
            json.dumps(
                {
                    "input_total": len(rows),
                    "bad_total": 0,
                    "message": "no bad rows; merged copied from input",
                    "merged_out": str(merged_out),
                },
                ensure_ascii=False,
            )
        )
        return 0

    mod = load_batch_module()
    retry_rows: List[Dict[str, Any]] = []
    for src_row in bad:
        retry_rows.append(retry_one(mod, src_row, retries=max(1, args.retries)))

    write_jsonl(retry_out, retry_rows)
    merged_rows, replacement = merge_rows(rows, retry_rows)
    write_jsonl(merged_out, merged_rows)

    retry_success = [r for r in retry_rows if r.get("status") == "success"]
    retry_failed = [r for r in retry_rows if r.get("status") != "success"]
    summary = {
        "input_total": len(rows),
        "bad_total": len(bad),
        "retry_success": len(retry_success),
        "retry_failed": len(retry_failed),
        "retry_failed_indexes": [r.get("customer_index") for r in retry_failed],
        "retry_out": str(retry_out),
        "merged_out": str(merged_out),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
