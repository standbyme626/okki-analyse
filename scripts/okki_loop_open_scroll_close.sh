#!/usr/bin/env bash
set -euo pipefail

AB=(agent-browser --session okki)
LOG="logs/okki-loop-open-scroll-close.jsonl"
mkdir -p logs screenshots

open_row_by_index() {
  local idx="$1"
  "${AB[@]}" eval "(() => {
    const rows=[...document.querySelectorAll('div')].filter(d => (d.className||'').includes('row-item-level-1') && (d.className||'').includes('__virtual_list_default_class__'));
    const row=rows[$idx];
    if(!row) return 'NO_ROW_$idx';
    const target=row.querySelector('p span.truncate, p .truncate, p span, p') || row;
    const name=(target.textContent||row.textContent||'').trim().replace(/\\s+/g,' ').slice(0,80);
    target.click();
    return 'OPEN_ROW_$idx name=' + name;
  })()"
}

scroll_to_customer_level() {
  "${AB[@]}" eval "(() => {
    const panel=[...document.querySelectorAll('div')].find(d => (d.className||'').includes('space-container-content') && (d.className||'').includes('overflow-auto'));
    if(!panel) return 'NO_PANEL';
    const label=[...panel.querySelectorAll('label,.ow-detail-fields__item-label label')].find(x => (x.textContent||'').trim()==='客户等级');
    if(!label) return 'NO_LEVEL_LABEL';
    const top=label.getBoundingClientRect().top - panel.getBoundingClientRect().top + panel.scrollTop;
    panel.scrollTop=Math.max(0, top-120);
    return 'SCROLLED_TO_LEVEL scrollTop=' + panel.scrollTop;
  })()"
}

close_panel() {
  "${AB[@]}" eval "(() => {
    const btn=[...document.querySelectorAll('button')].find(b => {
      const path=b.querySelector('svg path[d*=\"M8 8 32 32\"], svg path[d*=\"m8 8 32 32\"]');
      return !!path;
    });
    if(!btn) return 'NO_CLOSE_BTN';
    btn.click();
    return 'CLOSED_PANEL';
  })()"
}

for i in $(seq 1 10); do
  ts=$(date +"%Y-%m-%d %H:%M:%S")

  r1=$(open_row_by_index 0 || true)
  "${AB[@]}" wait 500 >/dev/null || true
  s1=$(scroll_to_customer_level || true)
  "${AB[@]}" wait 300 >/dev/null || true
  c1=$(close_panel || true)
  "${AB[@]}" wait 500 >/dev/null || true

  r2=$(open_row_by_index 1 || true)
  "${AB[@]}" wait 500 >/dev/null || true
  s2=$(scroll_to_customer_level || true)
  "${AB[@]}" wait 300 >/dev/null || true
  c2=$(close_panel || true)
  "${AB[@]}" wait 500 >/dev/null || true

  printf '{"time":"%s","cycle":%d,"row1_open":"%s","row1_scroll":"%s","row1_close":"%s","row2_open":"%s","row2_scroll":"%s","row2_close":"%s"}\n' \
    "$ts" "$i" "$r1" "$s1" "$c1" "$r2" "$s2" "$c2" >> "$LOG"

done

"${AB[@]}" screenshot "screenshots/okki-loop-final.png" >/dev/null || true

echo "DONE"
echo "LOG=$LOG"
tail -n 10 "$LOG"
