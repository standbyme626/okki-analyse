"""Core spine models for browser-independent platform observations.

This module defines the stable data boundary that `sys` should expose to the
Windows-side Companion and the upstream business brain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .page_model import StructuredError


class PlatformName(str, Enum):
    OKKI = "okki"
    ALIBABA = "alibaba"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    REVIEW_ONLY = "review_only"


def build_action_id(prefix: str = "plan") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ObservationBundle:
    platform: str
    source: str
    url: str = ""
    title: str = ""
    page_text: str = ""
    playwright_snapshot: str = ""
    screenshot_paths: List[str] = field(default_factory=list)
    raw_payloads: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    collected_at: str = field(default_factory=utc_now_iso)

    def get_raw_payload(self, key: str, default: Any = None) -> Any:
        return self.raw_payloads.get(key, default)


@dataclass
class ActionIntent:
    name: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReadModel:
    platform: str
    page_kind: str
    page_mode: str = "unknown"
    customer_identity: Dict[str, Any] = field(default_factory=dict)
    structured_profile: Dict[str, Any] = field(default_factory=dict)
    contacts: List[Dict[str, Any]] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class PreparedActionPlan:
    ok: bool
    action_id: str
    platform: str
    intent: str
    page_mode: str
    risk_level: str
    approval_required: bool
    dry_run: bool
    proposed_changes: Dict[str, Any] = field(default_factory=dict)
    verify_checks: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    steps: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    forbidden_steps: List[str] = field(default_factory=list)
    error: Optional[StructuredError] = None
