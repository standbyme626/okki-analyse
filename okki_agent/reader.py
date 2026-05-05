"""Read-only field extractors for OKKI pages.

Safety boundary:
- Reader functions never click, type, submit, or save.
- Input should come from already-captured snapshot/text artifacts.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .page_model import (
    ActionPlan,
    PageMode,
    ReadResult,
    StructuredError,
    detect_page_mode,
    detect_profile_tab_state,
    detect_section_state,
)

SECTION_NAMES = ("公司常用信息", "公司其他信息", "跟进信息", "系统信息")
COMMON_INFO_FIELDS = (
    "公司网址",
    "公司名称",
    "简称",
    "国家地区",
    "客户来源",
    "客户阶段",
    "客户编号",
    "座机",
)
OTHER_INFO_FIELDS = (
    "客户类型",
    "年采购额",
    "采购意向",
    "时区",
    "规模",
    "产品分组",
    "传真",
    "详细地址",
    "公司备注",
    "公司logo",
    "客户代码",
    "客户等级",
    "客户销售渠道",
    "询盘产品",
)


def _extract_label_value(snapshot_text: str, label: str) -> Optional[str]:
    """Extract value after a `StaticText "<label>"` entry in snapshot text."""
    lines = snapshot_text.splitlines()
    needle = f'StaticText "{label}"'
    for idx, line in enumerate(lines):
        if needle in line:
            for nxt in lines[idx + 1 : idx + 8]:
                if "StaticText" not in nxt:
                    continue
                m = re.search(r'StaticText "(.*)"', nxt)
                if not m:
                    continue
                val = m.group(1).strip()
                if val and val != label:
                    return val
    return None


def _label_name_from_lines(lines: List[str], idx: int) -> Optional[str]:
    """Return label text when a LabelText block starts at index `idx`."""
    for j in range(idx + 1, min(idx + 6, len(lines))):
        m = re.search(r'StaticText "([^"]+)"', lines[j])
        if m:
            return m.group(1).strip()
    return None


def _next_boundary(lines: List[str], start_idx: int) -> int:
    """Find next section boundary line index."""
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        if 'StaticText "公司常用信息"' in line:
            return i
        if 'StaticText "公司其他信息"' in line:
            return i
        if 'StaticText "跟进信息"' in line:
            return i
        if 'StaticText "系统信息"' in line:
            return i
    return len(lines)


def _extract_section_block(snapshot_text: str, section_name: str) -> Optional[List[str]]:
    """Return lines for a section block delimited by section headers."""
    lines = snapshot_text.splitlines()
    start = None
    token = f'StaticText "{section_name}"'
    for i, line in enumerate(lines):
        if token in line:
            start = i
            break
    if start is None:
        return None
    end = _next_boundary(lines, start)
    # Skip the title line itself for field parsing.
    return lines[start + 1 : end]


def _parse_label_value_pairs(section_lines: List[str]) -> Dict[str, Optional[str]]:
    """Parse label-value pairs within one section block.

    The parser is resilient to missing fields and reordered fields, because it
    keys by semantic label text instead of position.
    """
    pairs: Dict[str, Optional[str]] = {}
    i = 0
    while i < len(section_lines):
        line = section_lines[i]
        if "LabelText" not in line:
            i += 1
            continue
        label = _label_name_from_lines(section_lines, i)
        if not label:
            i += 1
            continue

        value_tokens: List[str] = []
        j = i + 1
        while j < len(section_lines):
            nxt = section_lines[j]
            if "LabelText" in nxt:
                break
            if any(f'StaticText "{s}"' in nxt for s in SECTION_NAMES):
                break
            m = re.search(r'StaticText "([^"]+)"', nxt)
            if m:
                token = m.group(1).strip()
                if token and token != label:
                    value_tokens.append(token)
            j += 1

        if value_tokens:
            value = "".join(value_tokens).strip()
            pairs[label] = None if value in {"--", "无", ""} else value
        else:
            pairs[label] = None
        i = j
    return pairs


def read_profile_section_fields(snapshot_text: str, section_name: str) -> ReadResult:
    """Read all label-value fields from a profile section by section name.

    Supported section names include `公司常用信息` and `公司其他信息`.
    """
    if section_name not in SECTION_NAMES:
        return ReadResult(
            ok=False,
            error=StructuredError(
                code="unsupported_section",
                message=f"Unsupported section: {section_name}",
                details={"supported": list(SECTION_NAMES)},
            ),
        )

    block = _extract_section_block(snapshot_text, section_name)
    if block is None:
        return ReadResult(
            ok=False,
            error=StructuredError(
                code="section_not_found",
                message=f"Section not found: {section_name}",
            ),
        )

    pairs = _parse_label_value_pairs(block)
    return ReadResult(
        ok=True,
        value=pairs,
        confidence=0.9,
        evidence={"section_name": section_name, "field_count": len(pairs)},
    )


def read_profile_tab(snapshot_text: str) -> ReadResult:
    """Read current detail-tab selection state.

    Returns selected tab and whether profile tab (`资料`) is selected.
    """
    state = detect_profile_tab_state(snapshot_text)
    return ReadResult(
        ok=True,
        value={
            "selected_tab": state.selected_tab,
            "is_profile_selected": state.is_profile_selected,
        },
        confidence=0.98 if state.selected_tab else 0.4,
        evidence={"reasons": state.reasons},
    )


def expand_profile_section(section_name: str, snapshot_text: str) -> ReadResult:
    """Build a read-only expansion recommendation for a profile section.

    Safety boundary:
    - This function does not click.
    - It only tells caller whether a safe expand click is needed.
    """
    state = detect_section_state(snapshot_text, section_name)
    if state.state == "missing":
        return ReadResult(
            ok=False,
            error=StructuredError(
                code="section_missing",
                message=f"Section not found: {section_name}",
                details={"reasons": state.reasons},
            ),
        )

    should_click = state.state == "collapsed"
    plan = ActionPlan(
        ok=True,
        action="expand_profile_section",
        page_mode=PageMode.UNKNOWN,
        dry_run=True,
        involves_write=False,
        steps=[
            "Ensure `资料` tab is selected.",
            f"Locate section title `{section_name}` by semantic text.",
            "Click section title/toggle only if section is collapsed.",
            "Re-snapshot and verify section state.",
        ],
        forbidden_steps=[
            "Use fixed @eXX refs across snapshots",
            "Use coordinate-based click",
            "Click any save/submit/edit action",
        ],
    )
    return ReadResult(
        ok=True,
        value={
            "section_name": section_name,
            "section_state": state.state,
            "should_click_to_expand": should_click,
            "safe_click_target": section_name,
            "plan": {
                "action": plan.action,
                "steps": plan.steps,
                "forbidden_steps": plan.forbidden_steps,
            },
        },
        confidence=0.9,
        evidence={"reasons": state.reasons},
    )


def read_section_fields(snapshot_text: str, section_name: str) -> ReadResult:
    """Read label:value pairs from a named section.

    Field-order independent; missing fields are represented as null by higher-level readers.
    """
    return read_profile_section_fields(snapshot_text, section_name)


def read_common_info_fields(snapshot_text: str) -> ReadResult:
    """Read `公司常用信息` block with known field normalization."""
    result = read_profile_section_fields(snapshot_text, "公司常用信息")
    if not result.ok:
        return result
    fields = {name: result.value.get(name) for name in COMMON_INFO_FIELDS}  # type: ignore[union-attr]
    extra = {k: v for k, v in result.value.items() if k not in COMMON_INFO_FIELDS}  # type: ignore[union-attr]
    return ReadResult(
        ok=True,
        value={"fields": fields, "extra_fields": extra},
        confidence=result.confidence,
        evidence=result.evidence,
    )


def read_other_info_fields(snapshot_text: str) -> ReadResult:
    """Read `公司其他信息` block with known field normalization."""
    result = read_profile_section_fields(snapshot_text, "公司其他信息")
    if not result.ok:
        return result
    fields = {name: result.value.get(name) for name in OTHER_INFO_FIELDS}  # type: ignore[union-attr]
    extra = {k: v for k, v in result.value.items() if k not in OTHER_INFO_FIELDS}  # type: ignore[union-attr]
    return ReadResult(
        ok=True,
        value={"fields": fields, "extra_fields": extra},
        confidence=result.confidence,
        evidence=result.evidence,
    )


def read_current_customer_profile(snapshot_text: str, url: str, title: str) -> ReadResult:
    """Read unified current-customer profile model from detail snapshot.

    Safety boundary:
    - Read-only extraction.
    - No browser interaction.
    """
    mode_detection = detect_page_mode(url, title, snapshot_text)
    mode = mode_detection.mode

    profile_tab = read_profile_tab(snapshot_text)
    common = read_common_info_fields(snapshot_text)
    other = read_other_info_fields(snapshot_text)
    identity = read_customer_identity(snapshot_text, mode)
    name = read_customer_name(snapshot_text, mode)
    level = read_customer_level(snapshot_text, mode)
    tags = read_customer_tags(snapshot_text, mode)

    common_value = common.value if common.ok else {"fields": {}, "extra_fields": {}}
    other_value = other.value if other.ok else {"fields": {}, "extra_fields": {}}
    common_fields = common_value.get("fields", {})
    other_fields = other_value.get("fields", {})
    extra_fields = {}
    extra_fields.update(common_value.get("extra_fields", {}))
    extra_fields.update(other_value.get("extra_fields", {}))

    def _get_identity(name_key: str) -> Optional[str]:
        rr = identity.get(name_key)
        if rr and rr.ok:
            return rr.value
        return None

    schema = {
        "page_mode": mode.value,
        "customer_identity": {
            "customer_name": name.value if name.ok else _get_identity("customer_name"),
            "company_name": _get_identity("company_name"),
            "country": _get_identity("country"),
            "website": common_fields.get("公司网址"),
            "email": _get_identity("email"),
            "phone": _get_identity("phone"),
        },
        "okki_status": {
            "customer_level": level.value if level.ok else None,
            "customer_stage": common_fields.get("客户阶段"),
            "customer_tags": tags.value if tags.ok else [],
            "owner": "Helen Li" if "Helen Li" in snapshot_text else None,
            "source_channel": common_fields.get("客户来源"),
        },
        "business_signals": {
            "has_order": None,
            "order_amount": None,
            "has_inquiry": None,
            "has_quote": None,
            "last_contact_time": _extract_label_value(snapshot_text, "最近联系时间"),
            "product_interest": [],
        },
        "sections": {
            "公司常用信息": common_fields,
            "公司其他信息": other_fields,
            "extra_fields": extra_fields,
            "missing_fields": [
                k
                for k, v in {**common_fields, **other_fields}.items()
                if v is None
            ],
        },
        "meta": {
            "profile_tab_state": profile_tab.value if profile_tab.ok else {},
            "mode_reasons": mode_detection.reasons,
        },
    }
    return ReadResult(
        ok=True,
        value=schema,
        confidence=0.9,
        evidence={
            "mode_detection": mode_detection.reasons,
            "profile_tab": profile_tab.evidence if profile_tab.ok else {},
        },
    )


def read_customer_name(snapshot_text: str, page_mode: PageMode) -> ReadResult:
    """Read customer name using semantic title landmarks."""
    m = re.search(r'heading "([^"]+)" \[level=2', snapshot_text)
    if m:
        return ReadResult(
            ok=True,
            value=m.group(1).strip(),
            confidence=0.98,
            evidence={"strategy": "heading level=2"},
        )
    return ReadResult(
        ok=False,
        error=StructuredError(
            code="name_not_found",
            message="Customer name heading not found in snapshot",
            details={"page_mode": page_mode.value},
        ),
    )


def read_customer_level(snapshot_text: str, page_mode: PageMode) -> ReadResult:
    """Read current customer level from `客户等级` field value."""
    value = _extract_label_value(snapshot_text, "客户等级")
    if value is None:
        return ReadResult(
            ok=False,
            error=StructuredError(
                code="level_not_found",
                message="Customer level field not found",
                details={"page_mode": page_mode.value},
            ),
        )
    normalized = None if value in {"--", "", "无"} else value
    return ReadResult(
        ok=True,
        value=normalized,
        confidence=0.95,
        evidence={"raw_value": value, "label": "客户等级"},
    )


def read_customer_tags(snapshot_text: str, page_mode: PageMode) -> ReadResult:
    """Read tags from `标签：` line in the customer summary area."""
    lines = snapshot_text.splitlines()
    tag_idx = None
    for i, line in enumerate(lines):
        if 'StaticText "标签："' in line:
            tag_idx = i
            break

    if tag_idx is None:
        return ReadResult(
            ok=False,
            error=StructuredError(
                code="tags_label_not_found",
                message="Tag label not found",
                details={"page_mode": page_mode.value},
            ),
        )

    # Conservative parse window: stop at the first owner/stage markers.
    window_lines: List[str] = []
    for line in lines[tag_idx + 1 : tag_idx + 30]:
        if 'StaticText "跟进人:"' in line or 'StaticText "客户阶段:"' in line:
            break
        window_lines.append(line)
    window = "\n".join(window_lines)

    token_matches = re.findall(r'StaticText "([^\"]+)"', window)
    tags: List[str] = []
    for token in token_matches:
        t = token.strip()
        if not t:
            continue
        # strict filter to avoid polluting tags with summary/owner text
        if t in {"标签：", "跟进人:", "客户阶段:", "无"}:
            continue
        if any(ch in t for ch in [":", "：", " ", "。"]):
            continue
        if len(t) > 30:
            continue
        tags.append(t)

    # Most snapshots render tags as chips with minimal text.
    # Prefer empty list over false positives.
    return ReadResult(
        ok=True,
        value=tags,
        confidence=0.45 if not tags else 0.7,
        evidence={"strategy": "summary-line strict parse", "window_size": len(window_lines)},
    )


def read_customer_identity(snapshot_text: str, page_mode: PageMode) -> Dict[str, ReadResult]:
    """Read commonly needed identity fields from snapshot text."""
    company = _extract_label_value(snapshot_text, "公司名称")
    country = _extract_label_value(snapshot_text, "国家地区")
    phone = _extract_label_value(snapshot_text, "座机")
    email = _extract_label_value(snapshot_text, "邮箱")

    def to_result(value: Optional[str], label: str, conf: float) -> ReadResult:
        normalized = None if value in {None, "--", "无"} else value
        return ReadResult(
            ok=True,
            value=normalized,
            confidence=conf,
            evidence={"label": label, "raw_value": value},
        )

    return {
        "customer_name": read_customer_name(snapshot_text, page_mode),
        "company_name": to_result(company, "公司名称", 0.96),
        "country": to_result(country, "国家地区", 0.95),
        "phone": to_result(phone, "座机", 0.90),
        "email": to_result(email, "邮箱", 0.35),
    }
