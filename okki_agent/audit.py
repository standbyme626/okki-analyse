"""Audit helpers for OKKI automation artifacts.

Safety boundary:
- File logging only; no browser actions.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class AuditEvent:
    timestamp: str
    objective: str
    page_mode: str
    start_url: str
    dry_run: bool
    action: str
    success: bool
    customer_name: Optional[str] = None
    old_level: Optional[str] = None
    new_level: Optional[str] = None
    old_tags: List[str] = field(default_factory=list)
    proposed_tags: List[str] = field(default_factory=list)
    applied_tags: List[str] = field(default_factory=list)
    screenshot_paths: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


def append_audit_event(path: str, event: AuditEvent) -> None:
    """Append one JSONL audit event.

    Caller is responsible for passing accurate dry_run/write metadata.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")


def build_recon_event(
    objective: str,
    page_mode: str,
    start_url: str,
    action: str,
    success: bool,
    screenshot_paths: Optional[List[str]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    """Create a standard recon-phase event (always dry_run=True)."""
    return AuditEvent(
        timestamp=_now_iso(),
        objective=objective,
        page_mode=page_mode,
        start_url=start_url,
        dry_run=True,
        action=action,
        success=success,
        screenshot_paths=screenshot_paths or [],
        details=details or {},
    )
