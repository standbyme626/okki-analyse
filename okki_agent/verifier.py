"""Verification helpers for post-write readback.

Safety boundary:
- This module performs comparisons only.
- It does not trigger browser actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .page_model import PageMode


@dataclass
class VerifyResult:
    ok: bool
    page_mode: PageMode
    checks: List[str] = field(default_factory=list)
    mismatches: List[str] = field(default_factory=list)


def verify_after_write(
    page_mode: PageMode,
    expected_level: Optional[str],
    observed_level: Optional[str],
    expected_tags: List[str],
    observed_tags: List[str],
) -> VerifyResult:
    """Compare expected and observed field values.

    Designed for readback verification after an explicitly approved write flow.
    """
    checks: List[str] = []
    mismatches: List[str] = []

    if expected_level is not None:
        checks.append(f"level expected={expected_level} observed={observed_level}")
        if expected_level != observed_level:
            mismatches.append("customer_level_mismatch")

    expected_tag_set = {t.strip() for t in expected_tags if t and t.strip()}
    observed_tag_set = {t.strip() for t in observed_tags if t and t.strip()}
    checks.append(
        f"tags expected_subset={sorted(expected_tag_set)} observed={sorted(observed_tag_set)}"
    )
    if not expected_tag_set.issubset(observed_tag_set):
        mismatches.append("customer_tags_missing")

    return VerifyResult(
        ok=len(mismatches) == 0,
        page_mode=page_mode,
        checks=checks,
        mismatches=mismatches,
    )
