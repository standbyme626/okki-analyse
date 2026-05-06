"""Read-only Alibaba placeholder adapter for the sys spine.

This module intentionally does not own browser actions. It only turns browser
observations into platform summaries and placeholder plans.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .core_models import (
    ActionIntent,
    ObservationBundle,
    PreparedActionPlan,
    ReadModel,
    RiskLevel,
    build_action_id,
)
from .page_model import StructuredError

_ALIBABA_URL_HINTS = (
    "message.alibaba",
    "alicrm.alibaba",
    "my.alibaba",
)
_RIGHT_PANEL_HINTS = (
    "客户信息",
    "客户行为数据",
    "买家标签",
    "最近询盘产品",
)
_INQUIRY_HINTS = (
    "询盘",
    "Inquiry",
    "RFQ",
    "TM",
)


def _joined_text(bundle: ObservationBundle) -> str:
    return "\n".join(
        part for part in [bundle.title, bundle.page_text, bundle.playwright_snapshot] if part
    )


def detect_alibaba_page_kind(bundle: ObservationBundle) -> str:
    url = (bundle.url or "").lower()
    text = _joined_text(bundle)
    if any(hint in url for hint in _ALIBABA_URL_HINTS):
        if any(hint in text for hint in _RIGHT_PANEL_HINTS):
            return "alibaba_inquiry_with_right_panel"
        if any(hint in text for hint in _INQUIRY_HINTS):
            return "alibaba_inquiry_page"
        return "alibaba_page"
    if any(hint in text for hint in _RIGHT_PANEL_HINTS):
        return "alibaba_right_panel"
    return "unknown"


def observe_alibaba_inquiry(bundle: ObservationBundle) -> ReadModel:
    page_kind = detect_alibaba_page_kind(bundle)
    excerpt_lines = [
        line.strip()
        for line in (bundle.page_text or bundle.playwright_snapshot or "").splitlines()
        if line.strip()
    ]
    excerpt = "\n".join(excerpt_lines[:20])
    return ReadModel(
        platform="alibaba",
        page_kind=page_kind,
        page_mode="unknown",
        customer_identity={},
        structured_profile={
            "title": bundle.title,
            "url": bundle.url,
            "page_excerpt": excerpt,
            "right_panel_first": True,
            "raw_payload_keys": sorted(bundle.raw_payloads.keys()),
        },
        evidence={
            "source": bundle.source,
            "screenshot_paths": list(bundle.screenshot_paths),
        },
        warnings=[
            "Alibaba adapter is read-only in this phase.",
            "Use right-panel-first reading before any inquiry judgment.",
            "Real send/save actions remain outside sys and must stay in review.",
        ],
    )


def prepare_alibaba_action(intent: ActionIntent, bundle: ObservationBundle) -> PreparedActionPlan:
    page_kind = detect_alibaba_page_kind(bundle)
    if intent.name == "draft_reply":
        steps = [
            "Read the right-side customer panel first.",
            "Read the left-side inquiry body and product context.",
            "Send evidence to the business brain for reply draft generation.",
            "Stop before any Alibaba send action.",
        ]
        proposed_changes: Dict[str, Any] = {"draft_only": True}
    elif intent.name == "sync_to_okki":
        steps = [
            "Read the Alibaba right panel first.",
            "Extract customer identity and inquiry summary.",
            "Prepare an OKKI sync plan for review.",
            "Stop before any save or send action.",
        ]
        proposed_changes = {"sync_target": "okki", "draft_only": True}
    else:
        return PreparedActionPlan(
            ok=False,
            action_id=build_action_id("alibaba"),
            platform="alibaba",
            intent=intent.name,
            page_mode="unknown",
            risk_level=RiskLevel.REVIEW_ONLY.value,
            approval_required=True,
            dry_run=True,
            error=StructuredError(
                code="unsupported_alibaba_intent",
                message=f"Unsupported Alibaba intent: {intent.name}",
                details={"supported": ["draft_reply", "sync_to_okki"]},
            ),
            evidence={"page_kind": page_kind, "url": bundle.url},
        )

    return PreparedActionPlan(
        ok=True,
        action_id=build_action_id("alibaba"),
        platform="alibaba",
        intent=intent.name,
        page_mode="unknown",
        risk_level=RiskLevel.REVIEW_ONLY.value,
        approval_required=True,
        dry_run=True,
        proposed_changes=proposed_changes,
        verify_checks=[
            "Ensure no final business button is clicked in this phase.",
            "Ensure all Alibaba actions remain draft-only or review-only.",
        ],
        evidence={"page_kind": page_kind, "url": bundle.url},
        steps=steps,
        warnings=[
            "Placeholder plan only; no Alibaba mutation is allowed here.",
            "Final execution belongs to Playwright MCP on Windows after review.",
        ],
        forbidden_steps=[
            "Click Send",
            "Click Save",
            "Submit a final reply",
        ],
    )
