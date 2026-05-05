"""Page model primitives for OKKI automation.

Safety boundary:
- This module is read-only and planning-only.
- No browser mutation is performed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PageMode(str, Enum):
    DRAWER = "drawer"
    FULL_PAGE = "full_page"
    UNKNOWN = "unknown"


@dataclass
class StructuredError:
    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReadResult:
    ok: bool
    value: Any = None
    confidence: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    error: Optional[StructuredError] = None


@dataclass
class ActionPlan:
    ok: bool
    action: str
    page_mode: PageMode
    dry_run: bool
    involves_write: bool
    steps: List[str] = field(default_factory=list)
    forbidden_steps: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: Optional[StructuredError] = None


@dataclass
class PageModeDetection:
    mode: PageMode
    reasons: List[str]


@dataclass
class ProfileTabState:
    selected_tab: Optional[str]
    is_profile_selected: bool
    reasons: List[str]


@dataclass
class SectionState:
    section_name: str
    state: str  # expanded | collapsed | missing | unknown
    reasons: List[str]


def detect_page_mode(url: str, title: str, snapshot_text: str) -> PageModeDetection:
    """Detect page mode from URL/title/snapshot text.

    Detection is semantic and does not depend on ephemeral refs.
    """
    reasons: List[str] = []
    u = url or ""
    t = title or ""
    s = snapshot_text or ""

    if "/crm/customer/personal" in u:
        reasons.append("URL matches full-page detail route")
    if "客户详情" in t:
        reasons.append("Title indicates customer detail")
    if "公司常用信息" in s and "系统信息" in s:
        reasons.append("Detail sections exist in snapshot")

    if len(reasons) >= 2 and "/crm/customer/personal" in u:
        return PageModeDetection(mode=PageMode.FULL_PAGE, reasons=reasons)

    drawer_hints = [
        "客户列表",
        "请输入搜索关键字",
        "tab \"资料\"",
    ]
    drawer_hits = [h for h in drawer_hints if h in s]
    if drawer_hits and "客户详情" not in t:
        return PageModeDetection(
            mode=PageMode.DRAWER,
            reasons=["Likely list+drawer context", *drawer_hits],
        )

    return PageModeDetection(
        mode=PageMode.UNKNOWN,
        reasons=["Insufficient or conflicting signals"],
    )


def detect_profile_tab_state(snapshot_text: str) -> ProfileTabState:
    """Detect selected tab and whether `资料` is selected.

    Snapshot text may come from `snapshot` or `snapshot -i`.
    """
    s = snapshot_text or ""
    reasons: List[str] = []

    if 'tab "资料" [selected' in s:
        reasons.append("Found selected tab marker on `资料`")
        return ProfileTabState(selected_tab="资料", is_profile_selected=True, reasons=reasons)

    tab_candidates = ["动态", "资料", "商机&交易", "Tips", "AI 背调", "数据分析", "文档", "操作历史"]
    selected_tab: Optional[str] = None
    for tab in tab_candidates:
        if f'tab "{tab}" [selected' in s:
            selected_tab = tab
            reasons.append(f"Found selected tab marker on `{tab}`")
            break

    if selected_tab is None:
        reasons.append("No selected tab marker detected")
    return ProfileTabState(
        selected_tab=selected_tab,
        is_profile_selected=(selected_tab == "资料"),
        reasons=reasons,
    )


def detect_section_state(snapshot_text: str, section_name: str) -> SectionState:
    """Detect section visibility state by semantic anchors only.

    `expanded` means section header exists and at least one known field label is visible
    under that section context in the snapshot text.
    """
    s = snapshot_text or ""
    reasons: List[str] = []
    if f'StaticText "{section_name}"' not in s and f'generic "{section_name}"' not in s:
        return SectionState(section_name=section_name, state="missing", reasons=["section title not found"])

    reasons.append("section title found")
    if section_name == "公司常用信息":
        hints = ["公司网址", "公司名称", "国家地区", "客户来源", "客户编号", "座机"]
    elif section_name == "公司其他信息":
        hints = ["客户类型", "年采购额", "采购意向", "时区", "公司备注", "客户等级", "询盘产品"]
    else:
        hints = []

    hit_count = sum(1 for h in hints if f'StaticText "{h}"' in s)
    if hit_count >= 2:
        reasons.append(f"detected {hit_count} visible field labels")
        return SectionState(section_name=section_name, state="expanded", reasons=reasons)

    if hit_count == 0:
        reasons.append("no visible field labels detected")
        return SectionState(section_name=section_name, state="collapsed", reasons=reasons)

    reasons.append(f"detected only {hit_count} field label(s)")
    return SectionState(section_name=section_name, state="unknown", reasons=reasons)
