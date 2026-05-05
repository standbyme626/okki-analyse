"""Read-only helpers for OKKI customer list pages.

The OKKI list uses a virtual scroller: a 100-row page is not fully present in
the DOM at once. These helpers sweep the list container and de-duplicate rows by
company_id.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from .edge_bridge import _eval


DETAIL_ROUTE = "/crm/customer/personal"
DETAIL_URL_PREFIX = "https://crm.xiaoman.cn/crm/customer/personal?company_id="
LIST_API_PATH = "/api/customerV3Read/companyList"
LIST_SCROLLER_SELECTOR = ".vue-recycle-scroller.ready.direction-vertical.row-items"
NON_DEMO_NOTE = "auto_collected_non_demo"


@dataclass
class CustomerListRow:
    page: int
    page_row_index: int
    company_id: str
    customer_name: str
    customer_url: str
    country: str = ""
    last_contact: str = ""
    note: str = NON_DEMO_NOTE
    raw_name: str = ""
    href: str = ""
    virtual_top: int = 0
    is_demo: bool = False


def compact_customer_name(name: str) -> str:
    """Match the existing CSV convention: remove rendered spacing in names."""
    normalized = (name or "").replace("\u00a0", " ").strip()
    return re.sub(r"\s+", "", normalized)


def get_detail_url(company_id: str) -> str:
    return f"{DETAIL_URL_PREFIX}{company_id}"


def parse_company_id(url: str) -> str:
    m = re.search(r"[?&]company_id=([^&]+)", url or "")
    return m.group(1) if m else ""


def _rows_result(page: int, expected_page_size: int, raw_rows: List[CustomerListRow], **extra: Any) -> Dict[str, Any]:
    demo_rows = [row for row in raw_rows if row.is_demo]
    valid_rows = [row for row in raw_rows if not row.is_demo]
    result = {
        "page": page,
        "expected_page_size": expected_page_size,
        "raw_count": len(raw_rows),
        "demo_count": len(demo_rows),
        "valid_count": len(valid_rows),
        "rows": [asdict(row) for row in raw_rows],
        "valid_rows": [asdict(row) for row in valid_rows],
        "demo_rows": [asdict(row) for row in demo_rows],
    }
    result.update(extra)
    return result


def collect_list_page_rows_via_api(page: int, expected_page_size: int = 100) -> Dict[str, Any]:
    """Collect one list page from OKKI's read-only companyList endpoint.

    The browser UI already uses this endpoint to populate the list. Calling it
    from page context reuses the active login and current URL filters while
    avoiding virtual-scroller DOM gaps.
    """
    js = rf"""(async () => {{
      const query = JSON.parse(new URL(location.href).searchParams.get('query') || '{{}}');
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(query)) {{
        if (key === '_p_swarm_id') continue;
        if (Array.isArray(value)) {{
          value.forEach((v, i) => params.append(`${{key}}[${{i}}]`, String(v)));
        }} else if (value !== undefined && value !== null && value !== '') {{
          params.append(key, String(value));
        }}
      }}
      params.set('pageSize', String({int(expected_page_size)}));
      params.set('curPage', String({int(page)}));
      params.set('layout_flag', '1');

      const displayNames = new Intl.DisplayNames(['zh-CN'], {{type: 'region'}});
      const normName = s => (s || '').replace(/\u00a0/g, ' ').trim();
      const compactName = s => normName(s).replace(/\s+/g, '');
      const countryName = code => {{
        if (!code) return '';
        try {{ return displayNames.of(code) || code; }} catch (e) {{ return code; }}
      }};
      const regionLabel = row => {{
        const region = row.country_region || {{}};
        const country = region.country || row.country || '';
        const province = region.province || row.province || '';
        const city = region.city || row.city || '';
        return [countryName(country), province, city].filter(Boolean).join('/');
      }};
      const lastContact = row => {{
        const label = row.order_time_info && row.order_time_info.info_label;
        if (label) return label;
        if (row.order_time) return String(row.order_time).slice(0, 16);
        const trail = row.last_trail || {{}};
        return String(trail.create_time || trail.created_at || trail.update_time || '').slice(0, 16);
      }};

      const resp = await fetch('{LIST_API_PATH}', {{
        method: 'POST',
        credentials: 'include',
        headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
        body: params.toString(),
      }});
      const text = await resp.text();
      let data = null;
      try {{
        data = JSON.parse(text);
      }} catch (e) {{
        return JSON.stringify({{
          ok: false,
          status: resp.status,
          error: 'INVALID_JSON',
          text: text.slice(0, 500),
          request_body: params.toString(),
        }});
      }}
      const list = data && data.data && Array.isArray(data.data.list) ? data.data.list : [];
      return JSON.stringify({{
        ok: resp.ok && data.code === 0,
        status: resp.status,
        code: data && data.code,
        message: data && (data.msg || data.message || ''),
        request_body: params.toString(),
        total_item: data && data.data ? data.data.totalItem : null,
        rows: list.map(row => {{
          const rawName = normName((row.name_info && row.name_info.info_label) || row.name);
          const companyId = String(row.company_id || '');
          return {{
            company_id: companyId,
            raw_name: rawName,
            customer_name: compactName(rawName),
            customer_url: '{DETAIL_URL_PREFIX}' + companyId,
            href: '{DETAIL_ROUTE}?company_id=' + companyId,
            country: regionLabel(row),
            country_code: row.country || '',
            last_contact: lastContact(row),
            is_demo: rawName.startsWith('（示例）') || compactName(rawName).startsWith('（示例）'),
          }};
        }}),
      }});
    }})()"""
    payload = _eval(js, timeout_sec=30)
    if not payload or not payload.get("ok"):
        raise RuntimeError(f"Failed to read OKKI list API: {payload}")

    raw_rows: List[CustomerListRow] = []
    for index, row in enumerate(payload.get("rows", []), start=1):
        company_id = str(row.get("company_id") or "")
        raw_rows.append(
            CustomerListRow(
                page=page,
                page_row_index=index,
                company_id=company_id,
                customer_name=row.get("customer_name", ""),
                customer_url=row.get("customer_url") or get_detail_url(company_id),
                country=row.get("country", ""),
                last_contact=row.get("last_contact", ""),
                raw_name=row.get("raw_name", ""),
                href=row.get("href", ""),
                virtual_top=(index - 1) * 40,
                is_demo=bool(row.get("is_demo")),
            )
        )

    return _rows_result(
        page,
        expected_page_size,
        raw_rows,
        source="list_api",
        api_status=payload.get("status"),
        api_code=payload.get("code"),
        api_message=payload.get("message"),
        api_total_item=payload.get("total_item"),
        api_request_body=payload.get("request_body"),
    )


def get_list_page_state() -> Dict[str, Any]:
    js = r"""(() => {
      const pager = document.querySelector('.okki-pagination') || document;
      const active = pager.querySelector('.okki-pagination-item-active, .ant-pagination-item-active');
      const pageSize = [...pager.querySelectorAll('*')]
        .map(el => (el.textContent || '').trim())
        .find(text => /^\d+\s*条\/页$/.test(text));
      const totalText = [...pager.querySelectorAll('*')]
        .map(el => (el.textContent || '').trim())
        .find(text => /^共\s*\d+\s*条/.test(text));
      const scroller = document.querySelector('.vue-recycle-scroller.ready.direction-vertical.row-items')
        || [...document.querySelectorAll('div')].find(el =>
          String(el.className || '').includes('vue-recycle-scroller')
          && String(el.className || '').includes('row-items')
        );
      return JSON.stringify({
        location: location.href,
        title: document.title,
        current_page: active ? parseInt(active.textContent, 10) || null : null,
        page_size_text: pageSize || null,
        total_text: totalText || null,
        scroller_found: Boolean(scroller),
        scroller: scroller ? {
          scrollTop: scroller.scrollTop,
          clientHeight: scroller.clientHeight,
          scrollHeight: scroller.scrollHeight
        } : null
      });
    })()"""
    return _eval(js, timeout_sec=15)


def get_current_list_page() -> int:
    state = get_list_page_state()
    return int(state.get("current_page") or 0)


def _visible_row_signature() -> List[str]:
    rows = _read_visible_rows().get("visible", [])
    return [str(row.get("company_id") or "") for row in rows[:10] if row.get("company_id")]


def next_list_page(timeout_sec: float = 15.0) -> Dict[str, Any]:
    """Click OKKI list pagination next and wait until active page changes."""
    old_page = get_current_list_page()
    old_signature = _visible_row_signature()
    js = r"""(() => {
      const candidates = [
        ...document.querySelectorAll('li.okki-pagination-next[title="下一页"]'),
        ...document.querySelectorAll('li[title="下一页"]')
      ];
      const next = candidates.find(el =>
        !String(el.className || '').includes('disabled')
        && el.getAttribute('aria-disabled') !== 'true'
      );
      if (!next) return JSON.stringify({ok:false, error:'NEXT_NOT_FOUND'});
      const button = next.querySelector('button') || next;
      button.click();
      return JSON.stringify({ok:true, action:'CLICKED_NEXT'});
    })()"""
    clicked = _eval(js, timeout_sec=10)
    if not clicked.get("ok"):
        raise RuntimeError(f"Next page button not available: {clicked}")

    deadline = time.monotonic() + timeout_sec
    new_page = 0
    while time.monotonic() < deadline:
        time.sleep(0.5)
        current_page = get_current_list_page()
        if current_page and current_page != old_page:
            new_page = current_page
            break

    if not new_page:
        raise RuntimeError(
            f"Page did not change after next click: still on page {old_page} after {timeout_sec:.0f}s"
        )

    # OKKI updates active pagination before the virtual list finishes replacing
    # rows. Wait until the visible row signature changes before collecting data.
    while time.monotonic() < deadline:
        time.sleep(0.5)
        signature = _visible_row_signature()
        if signature and signature != old_signature:
            return {
                "old_page": old_page,
                "new_page": new_page,
                "click": clicked,
                "old_signature": old_signature,
                "new_signature": signature,
            }

    raise RuntimeError(
        f"Page changed from {old_page} to {new_page}, but list rows did not refresh before timeout"
    )


def _scroll_to(top: int) -> Dict[str, Any]:
    js = rf"""(() => {{
      const scroller = document.querySelector('{LIST_SCROLLER_SELECTOR}')
        || [...document.querySelectorAll('div')].find(el =>
          String(el.className || '').includes('vue-recycle-scroller')
          && String(el.className || '').includes('row-items')
        );
      if (!scroller) return JSON.stringify({{ok:false, error:'SCROLLER_NOT_FOUND'}});
      scroller.scrollTop = {int(top)};
      scroller.dispatchEvent(new Event('scroll', {{bubbles:true}}));
      return JSON.stringify({{
        ok: true,
        scrollTop: scroller.scrollTop,
        clientHeight: scroller.clientHeight,
        scrollHeight: scroller.scrollHeight
      }});
    }})()"""
    return _eval(js, timeout_sec=10)


def _read_visible_rows() -> Dict[str, Any]:
    js = rf"""(() => {{
      const normName = s => (s || '').replace(/\u00a0/g, ' ').trim();
      const compactName = s => normName(s).replace(/\s+/g, '');
      const abs = href => new URL(href, location.origin).href;
      const virtualTop = row => {{
        const view = row.closest('.vue-recycle-scroller__item-view');
        const style = view ? (view.getAttribute('style') || '') : '';
        const m = style.match(/translateY\((-?\d+(?:\.\d+)?)px\)/);
        return m ? Math.round(parseFloat(m[1])) : null;
      }};
      const scroller = document.querySelector('{LIST_SCROLLER_SELECTOR}')
        || [...document.querySelectorAll('div')].find(el =>
          String(el.className || '').includes('vue-recycle-scroller')
          && String(el.className || '').includes('row-items')
        );
      const rows = [...document.querySelectorAll('.row-item.row-item-level-1.__virtual_list_default_class__, .row-item-level-1')]
        .filter(row => row.querySelector('a[href*="{DETAIL_ROUTE}?company_id="]'))
        .map(row => {{
          const top = virtualTop(row);
          const a = row.querySelector('a[href*="{DETAIL_ROUTE}?company_id="]');
          const cells = [...row.querySelectorAll(':scope > .cell')].map(cell => normName(cell.textContent));
          const href = a.getAttribute('href') || '';
          const url = abs(href);
          const m = url.match(/[?&]company_id=([^&]+)/);
          const rawName = normName(a.textContent);
          return {{
            raw_name: rawName,
            customer_name: compactName(rawName),
            href,
            customer_url: url,
            company_id: m ? m[1] : '',
            last_contact: cells[6] || '',
            country: cells[7] || '',
            virtual_top: top,
            is_demo: rawName.startsWith('（示例）') || compactName(rawName).startsWith('（示例）')
          }};
        }})
        .filter(row => row.company_id && row.virtual_top !== null && row.virtual_top >= 0);
      return JSON.stringify({{
        scrollTop: scroller ? scroller.scrollTop : null,
        clientHeight: scroller ? scroller.clientHeight : null,
        scrollHeight: scroller ? scroller.scrollHeight : null,
        visible: rows
      }});
    }})()"""
    return _eval(js, timeout_sec=10)


def collect_current_page_rows(
    page: int,
    expected_page_size: int = 100,
    settle_sec: float = 0.35,
) -> Dict[str, Any]:
    """Collect one currently-open list page by sweeping the virtual scroller."""
    first_scroll = _scroll_to(0)
    if not first_scroll.get("ok"):
        raise RuntimeError(f"Customer list scroller not found: {first_scroll}")
    time.sleep(settle_sec)

    meta = _read_visible_rows()
    client_height = int(meta.get("clientHeight") or 0)
    scroll_height = int(meta.get("scrollHeight") or 0)
    if client_height <= 0 or scroll_height <= 0:
        raise RuntimeError(f"Invalid list scroller dimensions: {meta}")

    estimated_row_height = max(20, int(scroll_height / max(1, expected_page_size)))
    step = max(40, estimated_row_height * 2)
    positions = list(range(0, scroll_height + step, step))
    if positions[-1] != scroll_height:
        positions.append(scroll_height)

    rows_by_company: Dict[str, Dict[str, Any]] = {}
    ordered_ids: List[str] = []
    sweeps: List[Dict[str, Any]] = []

    for position in positions:
        scroll_meta = _scroll_to(position)
        time.sleep(settle_sec)
        batch = _read_visible_rows()
        visible_rows = batch.get("visible", [])
        sweeps.append(
            {
                "target_scroll_top": position,
                "scroll_meta": scroll_meta,
                "actual_scroll_top": batch.get("scrollTop"),
                "visible_count": len(visible_rows),
            }
        )
        for row in visible_rows:
            company_id = row["company_id"]
            if company_id not in rows_by_company:
                rows_by_company[company_id] = row
                ordered_ids.append(company_id)

    raw_rows: List[CustomerListRow] = []
    sorted_ids = sorted(
        ordered_ids,
        key=lambda company_id: int(rows_by_company[company_id].get("virtual_top") or 0),
    )
    for index, company_id in enumerate(sorted_ids, start=1):
        row = rows_by_company[company_id]
        raw_rows.append(
            CustomerListRow(
                page=page,
                page_row_index=index,
                company_id=company_id,
                customer_name=row["customer_name"],
                customer_url=row["customer_url"],
                country=row.get("country", ""),
                last_contact=row.get("last_contact", ""),
                raw_name=row["raw_name"],
                href=row["href"],
                virtual_top=int(row.get("virtual_top") or 0),
                is_demo=bool(row["is_demo"]),
            )
        )

    return _rows_result(
        page,
        expected_page_size,
        raw_rows,
        source="dom_virtual_scroller",
        sweeps=sweeps,
    )


def reset_list_scroll_top() -> None:
    _scroll_to(0)
