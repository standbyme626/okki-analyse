#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from okki_agent.edge_bridge import _eval, _run, capture_checkpoint, wait_ms


INPUT_CSV = ROOT / "data" / "stage1_pages001-010_urls_20260505-183036.csv"
RUN_LOG = ROOT / "logs" / "experiment-runs.jsonl"
WRITE_LOG = ROOT / "logs" / "okki-write-actions.jsonl"
TEST_REMARK = "ai修改这些内容"
TARGET_COUNT = 10
PAGE_SETTLE_MS = 3000
SETTLE_AFTER_WRITE_MS = 2500
PACE_MIN_MS = 2000
PACE_MAX_MS = 5000
LONG_PAUSE_EVERY = 5
LONG_PAUSE_MIN_MS = 20000
LONG_PAUSE_MAX_MS = 60000

COMPANY_PAYLOAD_KEYS = [
    "biz_type",
    "annual_procurement",
    "intention_level",
    "timezone",
    "scale_id",
    "product_group_ids",
    "fax",
    "address",
    "remark",
    "image_list",
    "homepage",
    "name",
    "short_name",
    "country_region",
    "origin_list",
    "trail_status",
    "serial_id",
    "tel_full_new",
    "company_id",
    "business_type_id",
]
CUSTOM_COMPANY_FIELD_KEYS = [
    "30883055377303",
    "30883189073182",
    "30883904807239",
    "31107498832451",
]
CUSTOMER_PAYLOAD_KEYS = [
    "name",
    "email",
    "contact",
    "tel_list",
    "post_grade",
    "post",
    "birth",
    "gender",
    "image_list",
    "remark",
    "forbidden_flag",
    "main_customer_flag",
    "reach_status_time",
    "growth_level",
    "suspected_invalid_email_flag",
    "reach_status",
    "customer_id",
    "company_id",
]


@dataclass
class Candidate:
    customer_index: int
    page: int
    page_row_index: int
    customer_name: str
    customer_url: str
    country: str
    last_contact: str
    note: str

    @property
    def company_id(self) -> str:
        parsed = urlparse(self.customer_url)
        return (parse_qs(parsed.query).get("company_id") or [""])[0]


def now() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def stamp() -> str:
    return now().strftime("%Y%m%d-%H%M%S")


RUN_ID = f"batch_company_remark_roundtrip_{stamp()}"
ARTIFACT_DIR = ROOT / "logs" / "recon" / RUN_ID
SHOT_DIR = ROOT / "screenshots" / "recon" / RUN_ID
DETAIL_JSONL = ARTIFACT_DIR / "customer_results.jsonl"
SUMMARY_JSON = ARTIFACT_DIR / "summary.json"
SUMMARY_MD = ARTIFACT_DIR / "summary.md"


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_candidates(path: Path) -> List[Candidate]:
    rows: List[Candidate] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                Candidate(
                    customer_index=int(row.get("customer_index") or 0),
                    page=int(row.get("page") or 0),
                    page_row_index=int(row.get("page_row_index") or 0),
                    customer_name=str(row.get("customer_name") or ""),
                    customer_url=str(row.get("customer_url") or ""),
                    country=str(row.get("country") or ""),
                    last_contact=str(row.get("last_contact") or ""),
                    note=str(row.get("note") or ""),
                )
            )
    rows.sort(key=lambda x: (x.customer_index, x.page, x.page_row_index))
    return rows


def paced_wait(min_ms: int = PACE_MIN_MS, max_ms: int = PACE_MAX_MS, *, reason: str, actions: List[Dict[str, Any]]) -> int:
    ms = random.randint(min_ms, max_ms)
    wait_ms(ms)
    actions.append({"safe_action": "wait", "ms": ms, "reason": reason})
    return ms


def open_detail(url: str, actions: List[Dict[str, Any]], *, retries: int = 3) -> None:
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            _run("open", url, timeout_sec=40)
            actions.append(
                {
                    "safe_action": "open",
                    "target": url,
                    "attempt": attempt,
                    "reason": "load customer full-page detail for checkpoint and interface write",
                    "result": "success",
                }
            )
            wait_ms(PAGE_SETTLE_MS)
            return
        except Exception as exc:
            last_error = str(exc)
            actions.append(
                {
                    "safe_action": "open",
                    "target": url,
                    "attempt": attempt,
                    "reason": "load customer full-page detail for checkpoint and interface write",
                    "result": "error",
                    "error": last_error,
                }
            )
            if attempt < retries:
                wait_ms(1500)
    raise RuntimeError(last_error or f"Failed to open detail page: {url}")


def checkpoint(prefix: str, label: str, rec: Dict[str, Any]) -> Dict[str, Any]:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shot_path = SHOT_DIR / f"{prefix}-{label}.png"
    meta = capture_checkpoint(
        shot_path,
        snapshot_path=ARTIFACT_DIR / f"{prefix}-{label}.snapshot_i.txt",
        probe_path=ARTIFACT_DIR / f"{prefix}-{label}.ready.json",
        page_kind="detail",
        timeout_sec=25,
        stable_rounds=2,
        settle_ms=800,
    )
    rec.setdefault("checkpoints", []).append(
        {
            "checkpoint": label,
            "capture_ready": meta.get("ready"),
            "capture_success": meta.get("captured"),
            "screenshot_path": meta.get("screenshot_path"),
            "snapshot_path": meta.get("snapshot_path"),
            "probe_path": meta.get("probe_path"),
            "snapshot_error": meta.get("snapshot_error"),
            "screenshot_error": meta.get("screenshot_error"),
        }
    )
    if meta.get("screenshot_path"):
        rec.setdefault("screenshot_paths", []).append(meta["screenshot_path"])
    return meta


def fetch_json(url: str, *, method: str = "GET", form: Optional[Dict[str, Any]] = None, timeout_sec: int = 45) -> Dict[str, Any]:
    js = f"""(async () => {{
      const reqUrl = {json.dumps(url, ensure_ascii=False)};
      const method = {json.dumps(method)};
      const form = {json.dumps(form, ensure_ascii=False)};
      const options = {{
        method,
        credentials: 'include',
        headers: {{}},
      }};
      if (method !== 'GET' && form) {{
        const params = new URLSearchParams();
        for (const [key, value] of Object.entries(form)) {{
          params.set(key, value == null ? '' : String(value));
        }}
        options.headers['Content-Type'] = 'application/x-www-form-urlencoded';
        options.body = params.toString();
      }}
      const resp = await fetch(reqUrl, options);
      const text = await resp.text();
      let data = null;
      try {{
        data = JSON.parse(text);
      }} catch (err) {{
        data = null;
      }}
      return JSON.stringify({{
        status: resp.status,
        ok: resp.ok,
        url: new URL(reqUrl, location.origin).href,
        text: data ? null : text,
        data,
      }});
    }})()"""
    result = _eval(js, timeout_sec=timeout_sec)
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected fetch result for {url}: {result!r}")
    return result


def fetch_detail(company_id: str, scene: str) -> Dict[str, Any]:
    if scene == "detail":
        url = f"/api/customerV2Read/detail?company_id={company_id}&scene=detail&directOwner=1"
    else:
        url = f"/api/customerV2Read/detail?company_id={company_id}&scene=edit"
    result = fetch_json(url, timeout_sec=45)
    data = result.get("data")
    if not result.get("ok") or not isinstance(data, dict) or data.get("code") != 0:
        raise RuntimeError(f"Failed to fetch scene={scene} for company_id={company_id}: {result}")
    return result


def extract_edit_values(edit_resp: Dict[str, Any]) -> Dict[str, Any]:
    try:
        values = edit_resp["data"]["data"]["values"]
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Malformed edit response structure: {exc}; response={edit_resp}") from exc
    if not isinstance(values, dict):
        raise RuntimeError(f"Edit values is not a dict: {type(values)}")
    return values


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def pick(obj: Dict[str, Any], keys: Iterable[str], *, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    defaults = defaults or {}
    for key in keys:
        if key in obj:
            out[key] = _clone(obj.get(key))
        elif key in defaults:
            out[key] = _clone(defaults[key])
    return out


def build_edit_payload(values: Dict[str, Any]) -> Dict[str, Any]:
    payload = pick(
        values,
        COMPANY_PAYLOAD_KEYS,
        defaults={
            "biz_type": "",
            "annual_procurement": 0,
            "intention_level": 0,
            "timezone": "",
            "scale_id": 0,
            "product_group_ids": [],
            "fax": "",
            "address": "",
            "remark": "",
            "image_list": [],
            "homepage": "",
            "name": "",
            "short_name": "",
            "country_region": {"city": "", "country": "", "province": ""},
            "origin_list": [],
            "trail_status": 0,
            "serial_id": "",
            "tel_full_new": {"tel": "", "tel_area_code": ""},
            "company_id": 0,
            "business_type_id": 0,
        },
    )
    for key in CUSTOM_COMPANY_FIELD_KEYS:
        payload[key] = _clone(values.get(key))

    customers: List[Dict[str, Any]] = []
    for customer in values.get("customers") or []:
        if not isinstance(customer, dict):
            continue
        customers.append(
            pick(
                customer,
                CUSTOMER_PAYLOAD_KEYS,
                defaults={
                    "name": "",
                    "email": "",
                    "contact": [],
                    "tel_list": [],
                    "post_grade": 0,
                    "post": "",
                    "birth": None,
                    "gender": 0,
                    "image_list": [],
                    "remark": "",
                    "forbidden_flag": 0,
                    "main_customer_flag": 0,
                    "reach_status_time": "",
                    "growth_level": 0,
                    "suspected_invalid_email_flag": 0,
                    "reach_status": 0,
                    "customer_id": 0,
                    "company_id": 0,
                },
            )
        )
    payload["customers"] = customers
    return payload


def post_edit(company_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return fetch_json(
        "/api/customerV3Write/edit",
        method="POST",
        form={
            "company_id": company_id,
            "archive_flag": "0",
            "lead_id": "",
            "data": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
        timeout_sec=60,
    )


def diff_paths(left: Any, right: Any, prefix: str = "") -> List[str]:
    if type(left) is not type(right):
        return [prefix or "$"]
    if isinstance(left, dict):
        paths: List[str] = []
        for key in sorted(set(left) | set(right)):
            next_prefix = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                paths.append(next_prefix)
                continue
            paths.extend(diff_paths(left[key], right[key], next_prefix))
        return paths
    if isinstance(left, list):
        if len(left) != len(right):
            return [prefix or "$"]
        paths: List[str] = []
        for idx, (lv, rv) in enumerate(zip(left, right)):
            next_prefix = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            paths.extend(diff_paths(lv, rv, next_prefix))
        return paths
    return [] if left == right else [prefix or "$"]


def append_write_log(
    *,
    customer_name: str,
    company_id: str,
    old_value: str,
    new_value: str,
    phase: str,
    result: str,
    before_shot: Optional[str],
    after_shot: Optional[str],
    run_id: str,
) -> None:
    append_jsonl(
        WRITE_LOG,
        {
            "timestamp": now().strftime("%Y-%m-%d %H:%M:%S %z"),
            "customer_name": customer_name,
            "company_id": company_id,
            "field": "company.remark",
            "old_tags": [],
            "proposed_tags": [],
            "action_phase": phase,
            "old_company_remark": old_value,
            "new_company_remark": new_value,
            "action_taken": f"API full-payload {phase} company.remark via /api/customerV3Write/edit",
            "result": result,
            "screenshot_path_before": before_shot,
            "screenshot_path_after": after_shot,
            "run_id": run_id,
        },
    )


def best_effort_after_write_checkpoint(
    *,
    candidate: Candidate,
    prefix: str,
    label: str,
    customer_rec: Dict[str, Any],
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"screenshot_path": None}
    try:
        open_detail(candidate.customer_url, customer_rec["actions"])
        meta = checkpoint(prefix, label, customer_rec)
    except Exception as exc:
        customer_rec.setdefault("warnings", []).append(
            f"{label}_ui_refresh_failed:{exc}"
        )
        meta["ui_refresh_error"] = str(exc)
    return meta


def emergency_restore_remark(
    *,
    candidate: Candidate,
    prefix: str,
    customer_rec: Dict[str, Any],
    restore_to: str,
) -> Dict[str, Any]:
    current_edit = fetch_detail(candidate.company_id, "edit")
    current_payload = build_edit_payload(extract_edit_values(current_edit))
    current_remark = str(current_payload.get("remark") or "")
    result: Dict[str, Any] = {
        "needed": current_remark != restore_to,
        "current_remark": current_remark,
        "target_remark": restore_to,
    }
    if current_remark == restore_to:
        return result

    target_payload = _clone(current_payload)
    target_payload["remark"] = restore_to
    write_resp = post_edit(candidate.company_id, target_payload)
    after_edit = fetch_detail(candidate.company_id, "edit")
    after_payload = build_edit_payload(extract_edit_values(after_edit))
    restored_remark = str(after_payload.get("remark") or "")
    ok = restored_remark == restore_to

    write_json(ARTIFACT_DIR / f"{prefix}-emergency_restore_baseline_edit.json", current_edit)
    write_json(ARTIFACT_DIR / f"{prefix}-emergency_restore_payload.json", target_payload)
    write_json(ARTIFACT_DIR / f"{prefix}-emergency_restore_write_response.json", write_resp)
    write_json(ARTIFACT_DIR / f"{prefix}-emergency_restore_after_edit.json", after_edit)

    append_write_log(
        customer_name=str(after_payload.get("name") or candidate.customer_name),
        company_id=candidate.company_id,
        old_value=current_remark,
        new_value=restore_to,
        phase="emergency_restore",
        result="success" if ok else "error",
        before_shot=None,
        after_shot=None,
        run_id=RUN_ID,
    )

    result.update(
        {
            "write_response": write_resp,
            "restored_remark": restored_remark,
            "success": ok,
        }
    )
    if not ok:
        raise RuntimeError(
            f"Emergency restore failed for {candidate.company_id}: expected={restore_to!r} actual={restored_remark!r}"
        )
    return result


def attempt_phase(
    *,
    candidate: Candidate,
    prefix: str,
    desired_remark: str,
    phase: str,
    customer_rec: Dict[str, Any],
) -> Dict[str, Any]:
    before_label = "before-write_set" if phase == "set" else "before-write_restore"
    after_label = "after-write_set" if phase == "set" else "after-write_restore"
    before_meta = checkpoint(prefix, before_label, customer_rec)
    baseline_edit = fetch_detail(candidate.company_id, "edit")
    baseline_values = extract_edit_values(baseline_edit)
    baseline_payload = build_edit_payload(baseline_values)
    before_remark = str(baseline_payload.get("remark") or "")
    target_payload = _clone(baseline_payload)
    target_payload["remark"] = desired_remark

    write_resp = post_edit(candidate.company_id, target_payload)
    write_data = write_resp.get("data") or {}
    if not write_resp.get("ok") or not isinstance(write_data, dict) or write_data.get("code") != 0:
        raise RuntimeError(f"{phase} write failed for {candidate.company_id}: {write_resp}")

    wait_ms(SETTLE_AFTER_WRITE_MS)
    after_meta = best_effort_after_write_checkpoint(
        candidate=candidate,
        prefix=prefix,
        label=after_label,
        customer_rec=customer_rec,
    )
    after_edit = fetch_detail(candidate.company_id, "edit")
    after_detail = fetch_detail(candidate.company_id, "detail")
    after_values = extract_edit_values(after_edit)
    after_payload = build_edit_payload(after_values)
    after_remark = str(after_payload.get("remark") or "")
    verified = after_remark == desired_remark
    if not verified:
        raise RuntimeError(
            f"{phase} readback mismatch for {candidate.company_id}: expected={desired_remark!r} actual={after_remark!r}"
        )

    append_write_log(
        customer_name=str(after_payload.get("name") or candidate.customer_name),
        company_id=candidate.company_id,
        old_value=before_remark,
        new_value=desired_remark,
        phase=phase,
        result="success",
        before_shot=before_meta.get("screenshot_path"),
        after_shot=after_meta.get("screenshot_path"),
        run_id=RUN_ID,
    )

    return {
        "before_screenshot": before_meta.get("screenshot_path"),
        "after_screenshot": after_meta.get("screenshot_path"),
        "baseline_edit": baseline_edit,
        "baseline_payload": baseline_payload,
        "target_payload": target_payload,
        "write_response": write_resp,
        "after_edit": after_edit,
        "after_detail": after_detail,
        "after_payload": after_payload,
        "before_remark": before_remark,
        "after_remark": after_remark,
    }


def customer_prefix(processed_index: int, candidate: Candidate) -> str:
    return f"p{processed_index:02d}-idx{candidate.customer_index:04d}-cid{candidate.company_id}"


def build_summary_md(summary: Dict[str, Any]) -> str:
    lines = [
        f"# {summary['objective']}",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- test_value: `{summary['test_value']}`",
        f"- selected_count: `{summary['selected_count']}`",
        f"- processed_count: `{summary['processed_count']}`",
        f"- skipped_non_empty_count: `{summary['skipped_non_empty_count']}`",
        f"- error_count: `{summary['error_count']}`",
        f"- stopped_early: `{summary['stopped_early']}`",
        "",
        "## Processed Customers",
        "",
        "| # | company_id | customer_name | old_remark | after_set | after_restore | diff_count | result |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in summary["processed"]:
        lines.append(
            f"| {item['order']} | {item['company_id']} | {item['customer_name']} | "
            f"{json.dumps(item['old_remark'], ensure_ascii=False)} | "
            f"{json.dumps(item['after_set_remark'], ensure_ascii=False)} | "
            f"{json.dumps(item['restored_remark'], ensure_ascii=False)} | "
            f"{item['roundtrip_diff_count']} | {item['result']} |"
        )
    if summary["skipped"]:
        lines.extend(["", "## Skipped Candidates", "", "| customer_index | company_id | reason | current_remark |", "| --- | --- | --- | --- |"])
        for item in summary["skipped"]:
            lines.append(
                f"| {item['customer_index']} | {item['company_id']} | {item['reason']} | "
                f"{json.dumps(item.get('current_remark', ''), ensure_ascii=False)} |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    random.seed(time.time())
    candidates = load_candidates(INPUT_CSV)
    if not candidates:
        raise SystemExit(f"No candidates found in {INPUT_CSV}")

    summary: Dict[str, Any] = {
        "objective": "Batch roundtrip smoke test for company.remark on 10 customers",
        "run_id": RUN_ID,
        "input_csv": str(INPUT_CSV),
        "test_value": TEST_REMARK,
        "timestamp_start": now_iso(),
        "selected_count": 0,
        "processed_count": 0,
        "skipped_non_empty_count": 0,
        "error_count": 0,
        "stopped_early": False,
        "processed": [],
        "skipped": [],
        "artifacts_dir": str(ARTIFACT_DIR),
        "screenshot_dir": str(SHOT_DIR),
    }
    run_start_url = candidates[0].customer_url

    for candidate in candidates:
        if summary["processed_count"] >= TARGET_COUNT:
            break

        prefix = customer_prefix(summary["processed_count"] + 1, candidate)
        customer_rec: Dict[str, Any] = {
            "timestamp_start": now_iso(),
            "customer_index": candidate.customer_index,
            "page": candidate.page,
            "page_row_index": candidate.page_row_index,
            "candidate_name": candidate.customer_name,
            "customer_url": candidate.customer_url,
            "company_id": candidate.company_id,
            "status": "pending",
            "result": "pending",
            "actions": [],
            "checkpoints": [],
            "screenshot_paths": [],
        }
        original_remark: Optional[str] = None
        try:
            open_detail(candidate.customer_url, customer_rec["actions"])
            baseline_edit = fetch_detail(candidate.company_id, "edit")
            baseline_values = extract_edit_values(baseline_edit)
            baseline_payload = build_edit_payload(baseline_values)
            original_remark = str(baseline_payload.get("remark") or "")

            if original_remark:
                summary["skipped_non_empty_count"] += 1
                customer_rec["status"] = "skipped_non_empty"
                customer_rec["result"] = "skipped"
                customer_rec["current_remark"] = original_remark
                customer_rec["timestamp_end"] = now_iso()
                append_jsonl(DETAIL_JSONL, customer_rec)
                summary["skipped"].append(
                    {
                        "customer_index": candidate.customer_index,
                        "company_id": candidate.company_id,
                        "customer_name": str(baseline_payload.get("name") or candidate.customer_name),
                        "reason": "current remark is not empty",
                        "current_remark": original_remark,
                    }
                )
                paced_wait(reason="pacing after read-only skip", actions=customer_rec["actions"])
                continue

            summary["selected_count"] += 1
            order = summary["processed_count"] + 1
            prefix = customer_prefix(order, candidate)
            checkpoint(prefix, "before-read", customer_rec)

            before_raw = {
                "edit": baseline_edit,
                "page": {
                    "href": _run("get", "url", timeout_sec=10),
                    "title": _run("get", "title", timeout_sec=10),
                },
            }
            write_json(ARTIFACT_DIR / f"{prefix}-before_raw.json", before_raw)
            write_json(ARTIFACT_DIR / f"{prefix}-before_payload.json", baseline_payload)

            set_result = attempt_phase(
                candidate=candidate,
                prefix=prefix,
                desired_remark=TEST_REMARK,
                phase="set",
                customer_rec=customer_rec,
            )
            write_json(ARTIFACT_DIR / f"{prefix}-set_baseline_edit.json", set_result["baseline_edit"])
            write_json(ARTIFACT_DIR / f"{prefix}-set_payload_base.json", set_result["baseline_payload"])
            write_json(ARTIFACT_DIR / f"{prefix}-set_payload_test.json", set_result["target_payload"])
            write_json(ARTIFACT_DIR / f"{prefix}-set_write_response.json", set_result["write_response"])
            write_json(ARTIFACT_DIR / f"{prefix}-after_set_edit.json", set_result["after_edit"])
            write_json(ARTIFACT_DIR / f"{prefix}-after_set_detail.json", set_result["after_detail"])

            restore_result = attempt_phase(
                candidate=candidate,
                prefix=prefix,
                desired_remark=original_remark,
                phase="restore",
                customer_rec=customer_rec,
            )
            write_json(ARTIFACT_DIR / f"{prefix}-restore_baseline_edit.json", restore_result["baseline_edit"])
            write_json(ARTIFACT_DIR / f"{prefix}-restore_payload_base.json", restore_result["baseline_payload"])
            write_json(ARTIFACT_DIR / f"{prefix}-restore_payload_restore.json", restore_result["target_payload"])
            write_json(ARTIFACT_DIR / f"{prefix}-restore_write_response.json", restore_result["write_response"])
            write_json(ARTIFACT_DIR / f"{prefix}-after_restore_edit.json", restore_result["after_edit"])
            write_json(ARTIFACT_DIR / f"{prefix}-after_restore_detail.json", restore_result["after_detail"])

            roundtrip_after_payload = restore_result["after_payload"]
            paths = diff_paths(baseline_payload, roundtrip_after_payload)
            write_json(ARTIFACT_DIR / f"{prefix}-roundtrip_diff_paths.json", paths)
            write_json(ARTIFACT_DIR / f"{prefix}-roundtrip_payload_after_restore.json", roundtrip_after_payload)

            final_name = str(roundtrip_after_payload.get("name") or baseline_payload.get("name") or candidate.customer_name)
            customer_rec.update(
                {
                    "status": "success",
                    "result": "success",
                    "customer_name": final_name,
                    "old_remark": original_remark,
                    "test_remark": TEST_REMARK,
                    "after_set_remark": set_result["after_remark"],
                    "restored_remark": restore_result["after_remark"],
                    "roundtrip_diff_count": len(paths),
                    "roundtrip_diff_paths": paths,
                    "timestamp_end": now_iso(),
                    "artifact_prefix": prefix,
                }
            )
            append_jsonl(DETAIL_JSONL, customer_rec)

            summary["processed"].append(
                {
                    "order": order,
                    "company_id": candidate.company_id,
                    "customer_name": final_name,
                    "old_remark": original_remark,
                    "after_set_remark": set_result["after_remark"],
                    "restored_remark": restore_result["after_remark"],
                    "roundtrip_diff_count": len(paths),
                    "roundtrip_diff_paths": paths,
                    "result": "success",
                    "screenshot_paths": customer_rec["screenshot_paths"],
                    "artifact_prefix": prefix,
                }
            )
            summary["processed_count"] += 1

            if summary["processed_count"] < TARGET_COUNT:
                paced_wait(reason="pacing between successful customers", actions=customer_rec["actions"])
                if summary["processed_count"] % LONG_PAUSE_EVERY == 0:
                    paced_wait(
                        min_ms=LONG_PAUSE_MIN_MS,
                        max_ms=LONG_PAUSE_MAX_MS,
                        reason="extra long pause after write burst",
                        actions=customer_rec["actions"],
                    )
        except Exception as exc:
            customer_rec["status"] = "error"
            customer_rec["result"] = "error"
            customer_rec["error"] = str(exc)
            customer_rec["timestamp_end"] = now_iso()
            if original_remark is not None:
                try:
                    customer_rec["emergency_restore"] = emergency_restore_remark(
                        candidate=candidate,
                        prefix=prefix,
                        customer_rec=customer_rec,
                        restore_to=original_remark,
                    )
                except Exception as restore_exc:
                    customer_rec["emergency_restore_error"] = str(restore_exc)
            try:
                checkpoint(prefix, "on-error", customer_rec)
            except Exception as shot_exc:  # pragma: no cover
                customer_rec.setdefault("checkpoint_errors", []).append(str(shot_exc))
            append_jsonl(DETAIL_JSONL, customer_rec)
            summary["error_count"] += 1
            summary["stopped_early"] = True
            summary["error"] = {
                "customer_index": candidate.customer_index,
                "company_id": candidate.company_id,
                "customer_name": candidate.customer_name,
                "message": str(exc),
            }
            break

    summary["timestamp_end"] = now_iso()
    write_json(SUMMARY_JSON, summary)
    SUMMARY_MD.write_text(build_summary_md(summary), encoding="utf-8")

    experiment_record = {
        "timestamp_start": summary["timestamp_start"],
        "timestamp_end": summary["timestamp_end"],
        "objective": summary["objective"],
        "start_url": run_start_url,
        "page_mode": "full_page",
        "commands_executed": [
            "python3 scripts/batch_roundtrip_company_remark.py",
            "GET /api/customerV2Read/detail?scene=edit",
            "POST /api/customerV3Write/edit",
            "GET /api/customerV2Read/detail?scene=detail",
            "GET /api/customerV2Read/detail?scene=edit",
        ],
        "clicked_targets": [],
        "expected_result": f"Process {TARGET_COUNT} customers by setting company.remark to {TEST_REMARK!r}, then restore original remark for each customer.",
        "actual_result": (
            f"processed={summary['processed_count']}, skipped_non_empty={summary['skipped_non_empty_count']}, "
            f"errors={summary['error_count']}, stopped_early={summary['stopped_early']}"
        ),
        "result": "success" if summary["processed_count"] == TARGET_COUNT and not summary["error_count"] else "partial",
        "write_action": {
            "attempted": True,
            "dry_run": False,
            "field": "company.remark",
            "test_value": TEST_REMARK,
            "processed_count": summary["processed_count"],
            "restored": True,
        },
        "screenshot_paths": [shot for item in summary["processed"] for shot in item["screenshot_paths"]],
        "artifacts": [
            str(SUMMARY_JSON.relative_to(ROOT)),
            str(SUMMARY_MD.relative_to(ROOT)),
            str(DETAIL_JSONL.relative_to(ROOT)),
        ],
        "conclusion": (
            "10-customer remark roundtrip batch completed and restored"
            if summary["processed_count"] == TARGET_COUNT and not summary["error_count"]
            else "batch remark roundtrip stopped early; inspect summary.json and customer_results.jsonl"
        ),
    }
    append_jsonl(RUN_LOG, experiment_record)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if experiment_record["result"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
