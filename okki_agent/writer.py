"""Write planning and low-level execution helpers for OKKI.

Safety boundary:
- Protected fields are hard-blocked from any write attempt.
- Planner functions default to dry_run=True.
- Caller should use explicit save/cancel control.
"""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any, Dict, List, Optional, Set

from .edge_bridge import _eval as _ab_eval, _run as _ab_run
from .page_model import ActionPlan, PageMode, StructuredError

_ALLOWED_LEVELS: Set[str] = {"A", "A-", "B", "B-", "C", "D"}
_FIELD_KEY_BY_LABEL: Dict[str, str] = {
    "详细地址": "address",
    "公司备注": "remark",
    "客户类型": "biz_type",
    "年采购额": "annual_procurement",
    "规模": "scale_id",
    "客户等级": "30883189073182",
    "客户销售渠道": "30883904807239",
}
_PROTECTED_FIELD_LABELS: Set[str] = {
    "公司名称",
    "国家名称",
    "国家地区",
    "客户来源",
    "客户编号",
    "客户代码",
    "时区",
}
_NON_EMPTY_CONSTRAINED_FIELDS: Set[str] = {
    "年采购额",
}
_EMPTY_DISPLAY_VALUES: Set[Optional[str]] = {
    None,
    "",
    "--",
    "请选择",
    "无",
}


def prepare_switch_to_profile_tab(
    current_tab_hint: Optional[str],
    page_mode: PageMode,
    dry_run: bool = True,
) -> ActionPlan:
    """Build a safe plan to switch from non-profile tab to `资料`.

    Safety boundary:
    - This function only returns a plan.
    - No browser action is executed.
    """
    if not dry_run:
        return ActionPlan(
            ok=False,
            action="prepare_switch_to_profile_tab",
            page_mode=page_mode,
            dry_run=False,
            involves_write=False,
            error=StructuredError(
                code="write_blocked",
                message="Non-dry-run execution is blocked in recon skeleton",
            ),
        )

    steps = [
        "Inspect current selected tab in detail area.",
        "If current tab is not `资料`, click semantic tab text `资料`.",
        "Re-snapshot and verify tab `资料` is selected.",
    ]
    if current_tab_hint:
        steps.insert(1, f"Current tab hint: `{current_tab_hint}`.")

    return ActionPlan(
        ok=True,
        action="prepare_switch_to_profile_tab",
        page_mode=page_mode,
        dry_run=True,
        involves_write=False,
        steps=steps,
        forbidden_steps=[
            "Use fixed @eXX refs from stale snapshot",
            "Use fixed coordinates",
        ],
        warnings=["Navigation-only plan. No write action included."],
    )


def prepare_toggle_profile_section(
    section_name: str,
    expand: bool,
    page_mode: PageMode,
    dry_run: bool = True,
) -> ActionPlan:
    """Build plan to expand/collapse `公司常用信息` or `公司其他信息`.

    Safety boundary:
    - This function does not execute clicks.
    - It only returns planned semantic steps.
    """
    allowed = {"公司常用信息", "公司其他信息"}
    if section_name not in allowed:
        return ActionPlan(
            ok=False,
            action="prepare_toggle_profile_section",
            page_mode=page_mode,
            dry_run=dry_run,
            involves_write=False,
            error=StructuredError(
                code="invalid_section",
                message=f"Unsupported section name: {section_name}",
                details={"allowed_sections": sorted(allowed)},
            ),
        )

    if not dry_run:
        return ActionPlan(
            ok=False,
            action="prepare_toggle_profile_section",
            page_mode=page_mode,
            dry_run=False,
            involves_write=False,
            error=StructuredError(
                code="write_blocked",
                message="Non-dry-run execution is blocked in recon skeleton",
            ),
        )

    intent = "expand" if expand else "collapse"
    return ActionPlan(
        ok=True,
        action="prepare_toggle_profile_section",
        page_mode=page_mode,
        dry_run=True,
        involves_write=False,
        steps=[
            "Ensure `资料` tab is selected.",
            f"Locate section header `{section_name}` by semantic text.",
            f"Inspect section state (expanded/collapsed) using visible descendant labels.",
            f"If needed, click section header or adjacent toggle icon to {intent}.",
            "Re-snapshot and verify state change by field visibility count.",
        ],
        forbidden_steps=[
            "Assume fixed position of header",
            "Use fixed @eXX refs without fresh snapshot",
        ],
        warnings=["UI shape may vary by tenant; always verify state after toggle."],
    )


def find_customer_level_field(page_mode: PageMode) -> ActionPlan:
    """Return semantic locator plan for customer level field.

    No UI action is executed.
    """
    return ActionPlan(
        ok=True,
        action="find_customer_level_field",
        page_mode=page_mode,
        dry_run=True,
        involves_write=False,
        steps=[
            "Ensure detail context is visible (`资料` tab).",
            "Find semantic label text `客户等级`.",
            "Resolve nearest value node in same field container.",
        ],
        forbidden_steps=[
            "Use fixed @eXX refs in long-term logic",
            "Use fixed screen coordinates",
        ],
    )


def prepare_read_common_and_other_info(page_mode: PageMode) -> ActionPlan:
    """Build plan to read all fields under common/other company sections.

    Safety boundary:
    - Read-only intent.
    - No write or save action.
    """
    return ActionPlan(
        ok=True,
        action="prepare_read_common_and_other_info",
        page_mode=page_mode,
        dry_run=True,
        involves_write=False,
        steps=[
            "Switch to `资料` tab if needed.",
            "Ensure `公司常用信息` is expanded, then parse all label-value pairs by semantic labels.",
            "Ensure `公司其他信息` is expanded, then parse all label-value pairs by semantic labels.",
            "Record missing fields explicitly as null rather than failing on index mismatch.",
            "Store unknown extra labels under `extra_fields` for schema drift tracking.",
        ],
        forbidden_steps=[
            "Rely on fixed field order",
            "Stop at first missing field",
        ],
        warnings=[
            "Fields can be permission-dependent or tenant-dependent.",
            "Keep parser label-driven, not position-driven.",
        ],
    )


def find_customer_tags_area(page_mode: PageMode) -> ActionPlan:
    """Return semantic locator plan for customer tags area.

    No UI action is executed.
    """
    return ActionPlan(
        ok=True,
        action="find_customer_tags_area",
        page_mode=page_mode,
        dry_run=True,
        involves_write=False,
        steps=[
            "Find label `标签`/`标签：` in customer summary or profile section.",
            "Resolve sibling chip/input container.",
            "Read existing tag tokens before any write plan.",
        ],
        forbidden_steps=[
            "Assume tags are always rendered as plain text",
            "Use fixed @eXX refs in production",
        ],
    )


def prepare_set_customer_level(
    target_level: str,
    current_level: Optional[str],
    page_mode: PageMode,
    dry_run: bool = True,
) -> ActionPlan:
    """Build a level-change plan only; never saves.

    If dry_run=False is passed, function still blocks execution in this recon stage.
    """
    if target_level not in _ALLOWED_LEVELS:
        return ActionPlan(
            ok=False,
            action="prepare_set_customer_level",
            page_mode=page_mode,
            dry_run=dry_run,
            involves_write=True,
            error=StructuredError(
                code="invalid_level",
                message=f"Unsupported target level: {target_level}",
                details={"allowed_levels": sorted(_ALLOWED_LEVELS)},
            ),
        )

    if not dry_run:
        return ActionPlan(
            ok=False,
            action="prepare_set_customer_level",
            page_mode=page_mode,
            dry_run=False,
            involves_write=True,
            error=StructuredError(
                code="write_blocked",
                message="Real write is blocked in recon skeleton",
            ),
        )

    missing_change = current_level == target_level
    steps = [
        "Locate `客户等级` semantic field.",
        f"Compare current level with target `{target_level}`.",
    ]
    if missing_change:
        steps.append("No-op: target already equals current level.")
    else:
        steps.extend(
            [
                "Open level selector (plan only).",
                f"Select option `{target_level}` (plan only).",
                "Stop before any save/confirm action.",
            ]
        )

    return ActionPlan(
        ok=True,
        action="prepare_set_customer_level",
        page_mode=page_mode,
        dry_run=True,
        involves_write=True,
        steps=steps,
        forbidden_steps=[
            "Click 保存/提交/确认",
            "Execute write without explicit user approval",
        ],
        warnings=["Plan generated only. No browser mutation is executed."],
    )


def prepare_add_customer_tags(
    proposed_tags: List[str],
    existing_tags: List[str],
    page_mode: PageMode,
    dry_run: bool = True,
) -> ActionPlan:
    """Build a tag-add plan only; never saves."""
    normalized = [t.strip() for t in proposed_tags if t and t.strip()]
    existing = {t.strip() for t in existing_tags if t and t.strip()}
    missing = [t for t in normalized if t not in existing]

    if not dry_run:
        return ActionPlan(
            ok=False,
            action="prepare_add_customer_tags",
            page_mode=page_mode,
            dry_run=False,
            involves_write=True,
            error=StructuredError(
                code="write_blocked",
                message="Real write is blocked in recon skeleton",
            ),
        )

    return ActionPlan(
        ok=True,
        action="prepare_add_customer_tags",
        page_mode=page_mode,
        dry_run=True,
        involves_write=True,
        steps=[
            "Locate tags area by semantic anchor `标签`.",
            f"Compute missing tags: {missing}",
            "Open tag selector/input (plan only).",
            "Prepare to add only missing tags (plan only).",
            "Stop before any save/confirm action.",
        ],
        forbidden_steps=[
            "Batch apply without per-customer verification",
            "Click 保存/提交/确认",
        ],
        warnings=["Plan generated only. No browser mutation is executed."],
    )


# ---------------------------------------------------------------------------
# Executable operations (solidified from live OKKI interaction tests)
# ---------------------------------------------------------------------------


def _js_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def wait_ms(ms: int, session: str = "okki") -> str:
    """Pause in browser context for predictable UI settling."""
    _ab_run("wait", str(ms), session=session, timeout_sec=max(30, int(ms / 1000) + 10))
    return f"WAITED:{ms}"


def _normalize_label(label: str) -> str:
    return (label or "").replace("：", "").replace(":", "").replace(" ", "").strip()


def _block_if_protected_field(label: str) -> Optional[str]:
    """Return block marker when write is forbidden on the given label."""
    normalized = _normalize_label(label)
    protected = {_normalize_label(x) for x in _PROTECTED_FIELD_LABELS}
    if normalized in protected:
        return f"BLOCKED_FIELD:{label}"
    return None


def is_empty_like_value(value: Optional[str]) -> bool:
    """Return True if value should be treated as empty/unfilled."""
    if value is None:
        return True
    normalized = (value or "").strip()
    return normalized in _EMPTY_DISPLAY_VALUES


def enter_edit_mode(session: str = "okki") -> str:
    """Click top `编辑` button to enter editable mode."""
    js = """(() => {
      const norm=s=>(s||'').replace(/\\s+/g,'');
      const btn=[...document.querySelectorAll('button')]
        .find(b=>norm(b.innerText||b.textContent||'')==='编辑');
      if(!btn) return 'NO_TOP_EDIT';
      btn.click();
      return 'CLICK_TOP_EDIT';
    })()"""
    return str(_ab_eval(js, session=session))


def expand_common_info(session: str = "okki") -> str:
    """Click first `展开全部(选填)` button under company common info area."""
    js = """(() => {
      const btns=[...document.querySelectorAll('button')]
        .filter(b => (b.innerText||b.textContent||'').includes('展开全部'));
      if(!btns.length) return 'NO_EXPAND_BUTTON';
      btns[0].click();
      return 'CLICK_COMMON_EXPAND';
    })()"""
    return str(_ab_eval(js, session=session))


def save_changes(session: str = "okki") -> str:
    """Click `确定` button to commit current edit form."""
    js = """(() => {
      const norm=s=>(s||'').replace(/\\s+/g,'');
      const btn=[...document.querySelectorAll('button')].find(
        b => norm(b.innerText||b.textContent||'')==='确定' || norm(b.innerText||b.textContent||'')==='确 定'
      );
      if(!btn) return 'NO_CONFIRM';
      btn.click();
      return 'CLICK_CONFIRM';
    })()"""
    return str(_ab_eval(js, session=session))


def cancel_changes(session: str = "okki") -> str:
    """Click `取消` button to discard current edit form."""
    js = """(() => {
      const norm=s=>(s||'').replace(/\\s+/g,'');
      const btn=[...document.querySelectorAll('button')].find(
        b => norm(b.innerText||b.textContent||'')==='取消' || norm(b.innerText||b.textContent||'')==='取 消'
      );
      if(!btn) return 'NO_CANCEL';
      btn.click();
      return 'CLICK_CANCEL';
    })()"""
    return str(_ab_eval(js, session=session))


def set_text_field(label: str, value: str, session: str = "okki") -> str:
    """Set one text field by label via visible `paas-form-item` input/textarea.

    Proven stable for:
    - 详细地址 (address)
    - 公司备注 (remark)
    """
    blocked = _block_if_protected_field(label)
    if blocked:
        return blocked
    key = _FIELD_KEY_BY_LABEL.get(label)
    if not key:
        return f"NO_KEY:{label}"
    js = f"""(() => {{
      const key={_js_quote(key)};
      const value={_js_quote(value)};
      const visible=(el)=>{{const s=getComputedStyle(el),r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;}};
      const form=[...document.querySelectorAll('.paas-form-item[data-paas-field=\"'+key+'\"]')].filter(visible)[0];
      if(!form) return 'NO_FORM:'+key;
      const ctrl=form.querySelector('input,textarea,[contenteditable=true]');
      if(!ctrl) return 'NO_CTRL:'+key;
      if(ctrl.tagName==='INPUT' || ctrl.tagName==='TEXTAREA'){{
        ctrl.focus();
        ctrl.value=value;
        ctrl.dispatchEvent(new Event('input',{{bubbles:true}}));
        ctrl.dispatchEvent(new Event('change',{{bubbles:true}}));
      }} else {{
        ctrl.focus();
        ctrl.textContent=value;
        ctrl.dispatchEvent(new Event('input',{{bubbles:true}}));
      }}
      return 'SET_TEXT:'+key;
    }})()"""
    return str(_ab_eval(js, session=session))


def clear_select_field(label: str, session: str = "okki") -> str:
    """Clear one select field using right-side `×` icon.

    This uses `mousedown` + `click`, which proved necessary in this OKKI UI.
    """
    blocked = _block_if_protected_field(label)
    if blocked:
        return blocked
    key = _FIELD_KEY_BY_LABEL.get(label)
    if not key:
        return f"NO_KEY:{label}"
    js = f"""(() => {{
      const key={_js_quote(key)};
      const visible=(el)=>{{const s=getComputedStyle(el),r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;}};
      const form=[...document.querySelectorAll('.paas-form-item[data-paas-field=\"'+key+'\"]')].filter(visible)[0];
      if(!form) return 'NO_FORM:'+key;
      form.dispatchEvent(new MouseEvent('mouseenter',{{bubbles:true}}));
      const clear=form.querySelector('.okki-select-clear') || form.querySelector('.anticon-close-circle');
      if(!clear) return 'NO_CLEAR_ICON:'+key;
      clear.dispatchEvent(new MouseEvent('mousedown',{{bubbles:true,cancelable:true}}));
      clear.dispatchEvent(new MouseEvent('mouseup',{{bubbles:true,cancelable:true}}));
      clear.dispatchEvent(new MouseEvent('click',{{bubbles:true,cancelable:true}}));
      return 'CLEAR_SELECT:'+key;
    }})()"""
    return str(_ab_eval(js, session=session))


def select_first_option(label: str, session: str = "okki") -> str:
    """Open one select field by semantic label and choose first visible option.

    Strategy:
    - Prefer exact `data-paas-field` mapping when available.
    - Fallback to label-based row lookup when key mapping is missing.
    """
    blocked = _block_if_protected_field(label)
    if blocked:
        return blocked
    key = _FIELD_KEY_BY_LABEL.get(label)
    js = f"""(() => new Promise((resolve)=>{{
      const target={_js_quote(label)};
      const key={_js_quote(key or '')};
      const norm=s=>(s||'').replace(/\\s+/g,'').trim();
      const visible=(el)=>{{const s=getComputedStyle(el),r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;}};
      let opened=false;

      if(key){{
        const form=[...document.querySelectorAll('.paas-form-item[data-paas-field=\"'+key+'\"]')].find(visible);
        if(form){{
          const trigger=form.querySelector('.okki-select-selector,.ant-select-selector,[role=combobox],.okki-select,.ant-select');
          if(trigger){{
            trigger.dispatchEvent(new MouseEvent('mousedown',{{bubbles:true,cancelable:true}}));
            trigger.dispatchEvent(new MouseEvent('mouseup',{{bubbles:true,cancelable:true}}));
            trigger.dispatchEvent(new MouseEvent('click',{{bubbles:true,cancelable:true}}));
            const inp=form.querySelector('input');
            if(inp){{
              inp.dispatchEvent(new KeyboardEvent('keydown',{{key:'ArrowDown',code:'ArrowDown',bubbles:true}}));
            }}
            opened=true;
          }}
        }}
      }}

      if(!opened){{
        const item=[...document.querySelectorAll('.ow-detail-fields__item')]
          .find(it=>norm(it.querySelector('label')?.textContent||'')===norm(target));
        if(!item){{ resolve('NO_ITEM:'+target); return; }}
        const pen=item.querySelector('button.ow-detail-fields__edit-icon,button');
        if(!pen){{ resolve('NO_PEN:'+target); return; }}
        pen.click();
      }}
      setTimeout(()=>{{
        const dds=[...document.querySelectorAll('.okki-select-dropdown,.ant-select-dropdown,[role=listbox]')].filter(visible);
        const dd=dds[dds.length-1];
        if(!dd){{ resolve('NO_DROPDOWN:'+target); return; }}
        const opts=[...dd.querySelectorAll('[role=option], .okki-select-item-option, .ant-select-item-option, .okki-select-item')].filter(visible);
        const first=opts.find(o=>norm(o.textContent||''));
        if(!first){{ resolve('NO_OPTION:'+target); return; }}
        const txt=(first.textContent||'').replace(/\\s+/g,' ').trim();
        first.dispatchEvent(new MouseEvent('mousedown',{{bubbles:true,cancelable:true}}));
        first.dispatchEvent(new MouseEvent('mouseup',{{bubbles:true,cancelable:true}}));
        first.dispatchEvent(new MouseEvent('click',{{bubbles:true,cancelable:true}}));
        resolve('SET_FIRST:'+target+'=>'+txt);
      }}, 900);
    }}))()"""
    return str(_ab_eval(js, session=session, timeout_sec=40))


def read_visible_field_value(label: str, session: str = "okki") -> Optional[str]:
    """Read one visible field value by semantic label in read mode."""
    js = f"""(() => {{
      const target={_js_quote(label)};
      const norm=s=>(s||'').replace(/\\s+/g,' ').trim();
      const visible=(el)=>{{const s=getComputedStyle(el),r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;}};
      const it=[...document.querySelectorAll('.ow-detail-fields__item')].filter(visible)
        .find(x=>norm(x.querySelector('label')?.textContent||'')===target);
      if(!it) return null;
      const clone=it.cloneNode(true);
      clone.querySelectorAll('button,svg,i,[role=button]').forEach(x=>x.remove());
      const raw=norm(clone.textContent||'');
      const val=raw.startsWith(target) ? norm(raw.slice(target.length)) : raw;
      return val || null;
    }})()"""
    return _ab_eval(js, session=session)


def clear_select_field_to_empty(label: str, session: str = "okki") -> str:
    """Clear one select field to empty with icon-first and option fallback.

    Returns one of:
    - ALREADY_EMPTY:<key>
    - CLEARED_BY_ICON:<key>
    - CLEARED_BY_OPTION:<key>
    - CLEAR_FAILED:<key>:<current_value>
    """
    blocked = _block_if_protected_field(label)
    if blocked:
        return blocked
    if label in _NON_EMPTY_CONSTRAINED_FIELDS:
        return f"EMPTY_NOT_ALLOWED:{label}"
    key = _FIELD_KEY_BY_LABEL.get(label)
    if not key:
        return f"NO_KEY:{label}"

    js = f"""(() => new Promise((resolve)=>{{
      const key={_js_quote(key)};
      const visible=(el)=>{{const s=getComputedStyle(el),r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;}};
      const norm=s=>(s||'').replace(/\\s+/g,' ').trim();
      const emptyLike = (v)=>!v || v==='--' || v==='请选择' || v==='请 选 择' || v==='无';
      const form=[...document.querySelectorAll('.paas-form-item[data-paas-field=\"'+key+'\"]')].find(visible);
      if(!form){{ resolve('NO_FORM:'+key); return; }}
      const readCurrent=()=>{{
        const item=form.querySelector('.okki-select-selection-item,.ant-select-selection-item');
        const ph=form.querySelector('.okki-select-selection-placeholder,.ant-select-selection-placeholder');
        return item ? norm(item.textContent||'') : (ph ? norm(ph.textContent||'') : '');
      }};
      let cur=readCurrent();
      if(emptyLike(cur)){{ resolve('ALREADY_EMPTY:'+key); return; }}

      // try clear icon first
      form.dispatchEvent(new MouseEvent('mouseenter',{{bubbles:true}}));
      const clear=form.querySelector('.okki-select-clear,.ant-select-clear,.anticon-close-circle');
      if(clear){{
        clear.dispatchEvent(new MouseEvent('mousedown',{{bubbles:true,cancelable:true}}));
        clear.dispatchEvent(new MouseEvent('mouseup',{{bubbles:true,cancelable:true}}));
        clear.dispatchEvent(new MouseEvent('click',{{bubbles:true,cancelable:true}}));
      }}

      setTimeout(()=>{{
        cur=readCurrent();
        if(emptyLike(cur)){{ resolve('CLEARED_BY_ICON:'+key); return; }}

        // fallback: open dropdown and select explicit empty option.
        const trigger=form.querySelector('.okki-select-selector,.ant-select-selector,[role=combobox],.okki-select,.ant-select');
        if(!trigger){{ resolve('CLEAR_FAILED:'+key+':'+cur); return; }}
        trigger.dispatchEvent(new MouseEvent('mousedown',{{bubbles:true,cancelable:true}}));
        trigger.dispatchEvent(new MouseEvent('mouseup',{{bubbles:true,cancelable:true}}));
        trigger.dispatchEvent(new MouseEvent('click',{{bubbles:true,cancelable:true}}));

        setTimeout(()=>{{
          const dds=[...document.querySelectorAll('.okki-select-dropdown,.ant-select-dropdown,[role=listbox]')].filter(visible);
          const dd=dds[dds.length-1];
          if(!dd){{ resolve('CLEAR_FAILED:'+key+':NO_DROPDOWN'); return; }}
          const opts=[...dd.querySelectorAll('[role=option], .okki-select-item-option, .ant-select-item-option, .okki-select-item')].filter(visible);
          const emptyOpt=opts.find(o=>{{
            const t=norm(o.textContent||'');
            return t==='--' || t==='无' || t==='请选择' || t==='空';
          }});
          if(!emptyOpt){{ resolve('CLEAR_FAILED:'+key+':NO_EMPTY_OPTION'); return; }}
          emptyOpt.dispatchEvent(new MouseEvent('mousedown',{{bubbles:true,cancelable:true}}));
          emptyOpt.dispatchEvent(new MouseEvent('mouseup',{{bubbles:true,cancelable:true}}));
          emptyOpt.dispatchEvent(new MouseEvent('click',{{bubbles:true,cancelable:true}}));
          setTimeout(()=>{{
            cur=readCurrent();
            if(emptyLike(cur)) resolve('CLEARED_BY_OPTION:'+key);
            else resolve('CLEAR_FAILED:'+key+':'+cur);
          }}, 260);
        }}, 360);
      }}, 220);
    }}))()"""
    return str(_ab_eval(js, session=session, timeout_sec=45))


def select_option_by_text(label: str, target_text: str, session: str = "okki") -> str:
    """Set select field to a specific option text by semantic label.

    Returns:
    - SET_OPTION:<label>=><text>
    - NO_TARGET_OPTION:<label>=><target_text>
    - NO_DROPDOWN:<label>
    """
    blocked = _block_if_protected_field(label)
    if blocked:
        return blocked
    key = _FIELD_KEY_BY_LABEL.get(label)
    if not key:
        return f"NO_KEY:{label}"
    js = f"""(() => new Promise((resolve)=>{{
      const key={_js_quote(key)};
      const target={_js_quote(target_text or '')};
      const norm=s=>(s||'').replace(/\\s+/g,'').trim();
      const visible=(el)=>{{const s=getComputedStyle(el),r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;}};
      const form=[...document.querySelectorAll('.paas-form-item[data-paas-field=\"'+key+'\"]')].find(visible);
      if(!form){{ resolve('NO_FORM:'+key); return; }}
      if(form.scrollIntoView) form.scrollIntoView({{block:'center',inline:'nearest',behavior:'instant'}});
      const trigger=form.querySelector('.okki-select-selector,.ant-select-selector,[role=combobox],.okki-select,.ant-select');
      if(!trigger){{ resolve('NO_TRIGGER:'+key); return; }}
      const openDropdown=()=>{{
        trigger.dispatchEvent(new MouseEvent('mousedown',{{bubbles:true,cancelable:true}}));
        trigger.dispatchEvent(new MouseEvent('mouseup',{{bubbles:true,cancelable:true}}));
        trigger.dispatchEvent(new MouseEvent('click',{{bubbles:true,cancelable:true}}));
      }};
      openDropdown();
      setTimeout(()=>{{
        const dds=[...document.querySelectorAll('.okki-select-dropdown,.ant-select-dropdown,[role=listbox]')].filter(visible);
        const dd=dds[dds.length-1];
        if(!dd){{
          // one retry after refocus
          if(trigger.focus) trigger.focus();
          openDropdown();
        }}
        setTimeout(()=>{{
          const d2=[...document.querySelectorAll('.okki-select-dropdown,.ant-select-dropdown,[role=listbox]')].filter(visible);
          const dd2=d2[d2.length-1];
          if(!dd2){{ resolve('NO_DROPDOWN:'+key); return; }}
          const opts=[...dd2.querySelectorAll('[role=option], .okki-select-item-option, .ant-select-item-option, .okki-select-item')].filter(visible);
          const targetNorm=norm(target);
          let hit=opts.find(o=>norm(o.textContent||'')===targetNorm);
          if(!hit){{
            hit=opts.find(o=>norm(o.textContent||'').includes(targetNorm));
          }}
          if(!hit){{
            resolve('NO_TARGET_OPTION:'+key+'=>'+target);
            return;
          }}
          const text=(hit.textContent||'').replace(/\\s+/g,' ').trim();
          hit.dispatchEvent(new MouseEvent('mousedown',{{bubbles:true,cancelable:true}}));
          hit.dispatchEvent(new MouseEvent('mouseup',{{bubbles:true,cancelable:true}}));
          hit.dispatchEvent(new MouseEvent('click',{{bubbles:true,cancelable:true}}));
          resolve('SET_OPTION:'+label+'=>'+text);
        }}, 450);
      }}, 900);
    }}))()"""
    return str(_ab_eval(js, session=session, timeout_sec=45))


def set_customer_level_first(session: str = "okki") -> str:
    return select_first_option("客户等级", session=session)


def set_customer_sales_channel_first(session: str = "okki") -> str:
    return select_first_option("客户销售渠道", session=session)


def set_customer_type_first(session: str = "okki") -> str:
    return select_first_option("客户类型", session=session)


def set_annual_procurement_first(session: str = "okki") -> str:
    return select_first_option("年采购额", session=session)


def set_scale_first(session: str = "okki") -> str:
    return select_first_option("规模", session=session)


def set_company_remark(value: str, session: str = "okki") -> str:
    return set_text_field("公司备注", value, session=session)


def set_detail_address(value: str, session: str = "okki") -> str:
    return set_text_field("详细地址", value, session=session)


def clear_customer_level(session: str = "okki") -> str:
    return clear_select_field("客户等级", session=session)


def clear_customer_sales_channel(session: str = "okki") -> str:
    return clear_select_field("客户销售渠道", session=session)


def clear_customer_type(session: str = "okki") -> str:
    return clear_select_field("客户类型", session=session)


def clear_scale(session: str = "okki") -> str:
    return clear_select_field("规模", session=session)


def read_key_fields(session: str = "okki") -> Dict[str, Any]:
    """Read key fields from current page for verification."""
    js = """(() => {
      const labels=['公司名称','客户类型','年采购额','规模','详细地址','公司备注','客户等级','客户销售渠道'];
      const norm=s=>(s||'').replace(/\\s+/g,' ').trim();
      const visible=(el)=>{const s=getComputedStyle(el),r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;};
      const values={};
      for(const lb of labels){
        const it=[...document.querySelectorAll('.ow-detail-fields__item')].filter(visible)
          .find(x=>norm(x.querySelector('label')?.textContent||'')===lb);
        if(!it){ values[lb]=null; continue; }
        const clone=it.cloneNode(true);
        clone.querySelectorAll('button,svg,i,[role=button]').forEach(n=>n.remove());
        const raw=norm(clone.textContent||'');
        values[lb]=raw.startsWith(lb) ? norm(raw.slice(lb.length)) : raw;
      }
      const h2=(document.querySelector('h2')?.textContent||'').trim();
      return JSON.stringify({customer_name:h2, values}, null, 2);
    })()"""
    obj = _ab_eval(js, session=session)
    return obj if isinstance(obj, dict) else {"raw": obj}
