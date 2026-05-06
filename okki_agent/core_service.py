"""Browser-independent spine services for OKKI and Alibaba observations."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional

from .alibaba_adapter import observe_alibaba_inquiry, prepare_alibaba_action
from .audit import AuditEvent, build_recon_event
from .core_models import (
    ActionIntent,
    ObservationBundle,
    PreparedActionPlan,
    ReadModel,
    RiskLevel,
    build_action_id,
)
from .page_model import PageMode, StructuredError, detect_page_mode
from .reader import read_current_customer_profile
from .verifier import VerifyResult, verify_after_write
from .writer import (
    prepare_add_customer_tags,
    prepare_read_common_and_other_info,
    prepare_set_customer_level,
)

try:  # Optional transitional dependency until raw payload parsing is fully solidified.
    from .detail_page import extract_values as _extract_detail_values
    from .detail_page import flatten_contacts as _flatten_contacts
    from .detail_page import summarize_customer as _summarize_customer
except ImportError:  # pragma: no cover
    _extract_detail_values = None
    _flatten_contacts = None
    _summarize_customer = None


def _to_snapshot_text(bundle: ObservationBundle) -> str:
    return bundle.playwright_snapshot or bundle.page_text or ""


def _extract_company_id(url: str) -> str:
    match = re.search(r"[?&]company_id=([^&]+)", url or "")
    return match.group(1) if match else ""


def _coerce_page_mode(value: str) -> PageMode:
    try:
        return PageMode(value)
    except ValueError:
        return PageMode.UNKNOWN


def detect_okki_page_mode(bundle: ObservationBundle) -> PageMode:
    detection = detect_page_mode(bundle.url, bundle.title, _to_snapshot_text(bundle))
    return detection.mode


def _get_profile_value(read_model: ReadModel, key: str, default: Any = None) -> Any:
    if key in read_model.structured_profile:
        return read_model.structured_profile.get(key, default)
    okki_status = read_model.structured_profile.get("okki_status")
    if isinstance(okki_status, Mapping):
        return okki_status.get(key, default)
    return default


def _get_tags(read_model: ReadModel) -> List[str]:
    tags = _get_profile_value(read_model, "customer_tags", [])
    if isinstance(tags, list):
        return [str(tag).strip() for tag in tags if str(tag).strip()]
    return []


def _observe_okki_customer_from_raw(bundle: ObservationBundle, page_mode: PageMode) -> Optional[ReadModel]:
    if not (_extract_detail_values and _summarize_customer and _flatten_contacts):
        return None

    edit_raw = bundle.get_raw_payload("edit_scene_raw")
    if not isinstance(edit_raw, Mapping):
        return None

    try:
        edit_values = _extract_detail_values(edit_raw)
    except Exception as exc:  # pragma: no cover
        return ReadModel(
            platform="okki",
            page_kind="okki_customer_detail",
            page_mode=page_mode.value,
            errors=[f"failed_to_parse_edit_scene_raw: {exc}"],
            evidence={"raw_payload_keys": sorted(bundle.raw_payloads.keys())},
        )

    detail_values: Optional[Mapping[str, Any]] = None
    detail_raw = bundle.get_raw_payload("detail_scene_raw")
    if isinstance(detail_raw, Mapping):
        try:
            detail_values = _extract_detail_values(detail_raw)
        except Exception:
            detail_values = None

    company_id = str(bundle.metadata.get("company_id") or _extract_company_id(bundle.url))
    source_row = bundle.metadata.get("source_row")
    if not isinstance(source_row, Mapping):
        source_row = {}

    summary = _summarize_customer(
        company_id=company_id,
        customer_url=bundle.url,
        edit_values=edit_values,
        detail_values=detail_values,
        source_row=source_row,
    )
    contacts = _flatten_contacts(
        company_id=company_id,
        customer_index=int(bundle.metadata.get("customer_index") or 0),
        customer_url=bundle.url,
        edit_values=edit_values,
    )
    return ReadModel(
        platform="okki",
        page_kind="okki_customer_detail",
        page_mode=page_mode.value,
        customer_identity={
            "customer_name": summary.get("customer_name"),
            "company_name": summary.get("customer_name"),
            "country": summary.get("country"),
            "website": summary.get("website"),
            "email": summary.get("email"),
            "phone": summary.get("phone"),
        },
        structured_profile=summary,
        contacts=contacts,
        evidence={
            "raw_payload_keys": sorted(bundle.raw_payloads.keys()),
            "contact_count": len(contacts),
            "source": bundle.source,
        },
    )


def observe_okki_customer(bundle: ObservationBundle) -> ReadModel:
    page_mode = detect_okki_page_mode(bundle)
    raw_result = _observe_okki_customer_from_raw(bundle, page_mode)
    if raw_result is not None:
        return raw_result

    snapshot_text = _to_snapshot_text(bundle)
    if not snapshot_text:
        return ReadModel(
            platform="okki",
            page_kind="okki_unknown",
            page_mode=page_mode.value,
            errors=["missing_page_text_and_playwright_snapshot"],
            evidence={"url": bundle.url, "title": bundle.title},
        )

    profile_result = read_current_customer_profile(snapshot_text, bundle.url, bundle.title)
    if not profile_result.ok:
        error_message = profile_result.error.message if profile_result.error else "profile_read_failed"
        return ReadModel(
            platform="okki",
            page_kind="okki_unknown",
            page_mode=page_mode.value,
            errors=[error_message],
            evidence={"url": bundle.url, "title": bundle.title},
        )

    value = profile_result.value if isinstance(profile_result.value, Mapping) else {}
    return ReadModel(
        platform="okki",
        page_kind="okki_customer_detail",
        page_mode=page_mode.value,
        customer_identity=dict(value.get("customer_identity", {})),
        structured_profile=dict(value),
        contacts=[],
        evidence={
            "reader_evidence": profile_result.evidence,
            "source": bundle.source,
            "screenshot_paths": list(bundle.screenshot_paths),
        },
    )


def _wrap_plan(
    *,
    platform: str,
    intent: ActionIntent,
    page_mode: PageMode,
    base_plan: Any,
    proposed_changes: Optional[Dict[str, Any]] = None,
    verify_checks: Optional[List[str]] = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> PreparedActionPlan:
    risk_level = RiskLevel.HIGH.value if getattr(base_plan, "involves_write", False) else RiskLevel.LOW.value
    approval_required = bool(getattr(base_plan, "involves_write", False))
    return PreparedActionPlan(
        ok=bool(getattr(base_plan, "ok", False)),
        action_id=build_action_id("okki"),
        platform=platform,
        intent=intent.name,
        page_mode=page_mode.value,
        risk_level=risk_level,
        approval_required=approval_required,
        dry_run=bool(getattr(base_plan, "dry_run", True)),
        proposed_changes=proposed_changes or {},
        verify_checks=verify_checks or [],
        evidence=evidence or {},
        steps=list(getattr(base_plan, "steps", [])),
        warnings=list(getattr(base_plan, "warnings", [])),
        forbidden_steps=list(getattr(base_plan, "forbidden_steps", [])),
        error=getattr(base_plan, "error", None),
    )


def prepare_okki_action(intent: ActionIntent, bundle: ObservationBundle) -> PreparedActionPlan:
    observed = observe_okki_customer(bundle)
    page_mode = _coerce_page_mode(observed.page_mode)

    if intent.name == "read_customer_profile":
        base_plan = prepare_read_common_and_other_info(page_mode)
        return _wrap_plan(
            platform="okki",
            intent=intent,
            page_mode=page_mode,
            base_plan=base_plan,
            verify_checks=["Confirm the profile sections can be re-read after observation."],
            evidence={"customer_identity": observed.customer_identity},
        )

    if intent.name == "set_customer_level":
        target_level = str(intent.params.get("target_level") or "").strip()
        current_level = (
            _get_profile_value(observed, "level")
            or _get_profile_value(observed, "customer_level")
        )
        base_plan = prepare_set_customer_level(target_level, current_level, page_mode, dry_run=True)
        return _wrap_plan(
            platform="okki",
            intent=intent,
            page_mode=page_mode,
            base_plan=base_plan,
            proposed_changes={"customer_level": {"from": current_level, "to": target_level}},
            verify_checks=["Read back `客户等级` after an approved write."],
            evidence={"customer_identity": observed.customer_identity},
        )

    if intent.name == "add_customer_tags":
        proposed_tags = intent.params.get("tags") or []
        if not isinstance(proposed_tags, list):
            proposed_tags = [str(proposed_tags)]
        existing_tags = _get_tags(observed)
        base_plan = prepare_add_customer_tags(proposed_tags, existing_tags, page_mode, dry_run=True)
        return _wrap_plan(
            platform="okki",
            intent=intent,
            page_mode=page_mode,
            base_plan=base_plan,
            proposed_changes={"tags": {"existing": existing_tags, "proposed": proposed_tags}},
            verify_checks=["Read back tags after an approved write."],
            evidence={"customer_identity": observed.customer_identity},
        )

    return PreparedActionPlan(
        ok=False,
        action_id=build_action_id("okki"),
        platform="okki",
        intent=intent.name,
        page_mode=page_mode.value,
        risk_level=RiskLevel.REVIEW_ONLY.value,
        approval_required=True,
        dry_run=True,
        error=StructuredError(
            code="unsupported_okki_intent",
            message=f"Unsupported OKKI intent: {intent.name}",
            details={"supported": ["read_customer_profile", "set_customer_level", "add_customer_tags"]},
        ),
        evidence={"customer_identity": observed.customer_identity},
    )


def verify_okki_action(
    before_bundle: ObservationBundle,
    after_bundle: ObservationBundle,
    expected: Mapping[str, Any],
) -> VerifyResult:
    del before_bundle  # planned for future richer before/after diffing
    after_model = observe_okki_customer(after_bundle)
    page_mode = _coerce_page_mode(after_model.page_mode)
    expected_level = expected.get("target_level")
    expected_tags = expected.get("target_tags") or []
    if not isinstance(expected_tags, list):
        expected_tags = [str(expected_tags)]
    observed_level = (
        _get_profile_value(after_model, "level")
        or _get_profile_value(after_model, "customer_level")
    )
    observed_tags = _get_tags(after_model)
    return verify_after_write(
        page_mode=page_mode,
        expected_level=str(expected_level) if expected_level is not None else None,
        observed_level=str(observed_level) if observed_level is not None else None,
        expected_tags=[str(tag) for tag in expected_tags],
        observed_tags=observed_tags,
    )


def build_okki_audit_event(
    *,
    objective: str,
    bundle: ObservationBundle,
    action: str,
    success: bool,
    screenshot_paths: Optional[List[str]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    page_mode = detect_okki_page_mode(bundle)
    return build_recon_event(
        objective=objective,
        page_mode=page_mode.value,
        start_url=bundle.url,
        action=action,
        success=success,
        screenshot_paths=screenshot_paths or list(bundle.screenshot_paths),
        details=details or {},
    )


__all__ = [
    "detect_okki_page_mode",
    "observe_okki_customer",
    "observe_alibaba_inquiry",
    "prepare_okki_action",
    "prepare_alibaba_action",
    "verify_okki_action",
    "build_okki_audit_event",
]
