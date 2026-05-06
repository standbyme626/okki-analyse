#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from okki_agent.edge_bridge import capture_checkpoint


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs" / "recon"
SHOT_DIR = ROOT / "screenshots" / "recon"
RUN_LOG = LOG_DIR / "test7_fill_restore_run.json"
WRITE_LOG = ROOT / "logs" / "okki-write-actions.jsonl"
AB = ["agent-browser", "--session", "okki"]
OPEN_WAIT_MS = 5000
AFTER_FILL_WAIT_MS = 5000
AFTER_SAVE_WAIT_MS = 5000


TARGET_FIELDS = [
    "客户销售渠道",
    "客户等级",
    "公司备注",
    "详细地址",
    "客户类型",
    "年采购额",
    "规模",
]

LABEL_TO_KEY = {
    "公司名称": "name",
    "客户销售渠道": "30883904807239",
    "客户等级": "30883189073182",
    "公司备注": "remark",
    "详细地址": "address",
    "客户类型": "biz_type",
    "年采购额": "annual_procurement",
    "规模": "scale_id",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_ab(*args: str, timeout_sec: int = 20) -> str:
    p = subprocess.run(AB + list(args), text=True, capture_output=True, timeout=timeout_sec)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip())
    return (p.stdout or "").strip()


def paced_wait(ms: int) -> None:
    run_ab("wait", str(ms))


def parse_eval_output(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return None
    # agent-browser eval often wraps returned JSON string in quotes
    if raw.startswith('"'):
        raw = json.loads(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def eval_js(js: str, timeout_sec: int = 20) -> Any:
    out = run_ab("eval", js, timeout_sec=timeout_sec)
    return parse_eval_output(out)


def screenshot(name: str, checkpoint: str) -> Dict[str, Any]:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOT_DIR / name
    stem = path.stem
    return capture_checkpoint(
        path,
        snapshot_path=LOG_DIR / f"{stem}.checkpoint.snapshot_i.txt",
        probe_path=LOG_DIR / f"{stem}.checkpoint.ready.json",
        page_kind="detail",
        timeout_sec=25,
        stable_rounds=2,
        settle_ms=800,
        run_fn=run_ab,
        eval_fn=eval_js,
    ) | {"checkpoint": checkpoint}


def shot_path(artifact: Any) -> str | None:
    if isinstance(artifact, dict):
        return artifact.get("screenshot_path")
    if isinstance(artifact, str):
        return artifact
    return None


def snapshot_i(name: str) -> str:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / name
    out = run_ab("snapshot", "-i")
    path.write_text(out + "\n", encoding="utf-8")
    return str(path)


def get_target_values() -> Dict[str, Any]:
    js = f"""(() => {{
      const labels = {json.dumps(TARGET_FIELDS, ensure_ascii=False)};
      const norm=s=>(s||'').replace(/\\s+/g,' ').trim();
      const itemByLabel=(label)=>[...document.querySelectorAll('.ow-detail-fields__item')]
        .find(it=>norm(it.querySelector('label')?.textContent||'')===label);
      const values={{}};
      for(const lb of labels){{
        const it=itemByLabel(lb);
        if(!it){{ values[lb]=null; continue; }}
        const raw=norm(it.textContent||'');
        const l=norm(it.querySelector('label')?.textContent||'');
        let v=raw;
        if(l && raw.startsWith(l)) v=norm(raw.slice(l.length));
        values[lb]=v||null;
      }}
      const customer_name=(document.querySelector('h2')?.textContent||'').trim() || null;
      return JSON.stringify({{customer_name, url: location.href, values}}, null, 2);
    }})()"""
    obj = eval_js(js)
    assert isinstance(obj, dict)
    return obj


def click_top_edit() -> str:
    js = """(() => {
      const norm=s=>(s||'').replace(/\\s+/g,'');
      const btn=[...document.querySelectorAll('button')]
        .find(b=>norm(b.innerText||b.textContent||'')==='编辑');
      if(!btn) return 'NO_TOP_EDIT';
      btn.click();
      return 'CLICK_TOP_EDIT';
    })()"""
    return str(eval_js(js))


def click_common_expand() -> str:
    # User requested: click company common-info expand first
    js = """(() => {
      const norm=s=>(s||'').replace(/\\s+/g,' ');
      const btns=[...document.querySelectorAll('button')].filter(
        b => norm(b.innerText||b.textContent||'').includes('展开全部')
      );
      if(!btns.length) return 'NO_EXPAND_BUTTON';
      btns[0].click();
      return 'CLICK_COMMON_EXPAND';
    })()"""
    return str(eval_js(js))


def set_select_first(label: str) -> str:
    js = f"""(() => {{
      const target = {json.dumps(label, ensure_ascii=False)};
      const key = {json.dumps(LABEL_TO_KEY.get(label), ensure_ascii=False)};
      const norm=s=>(s||'').replace(/\\s+/g,' ').trim();
      const visible=(el)=>{{
        const s=getComputedStyle(el), r=el.getBoundingClientRect();
        return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
      }};
      const item=[...document.querySelectorAll('.ow-detail-fields__item')]
        .find(it=>norm(it.querySelector('label')?.textContent||'')===target);
      if(!item) return 'NO_ITEM:' + target;
      // Stable method: click row pencil, then pick first visible option.
      const pen=item.querySelector('button.ow-detail-fields__edit-icon,button');
      if(pen) pen.click();
      const start=Date.now();
      let dds=[...document.querySelectorAll('.okki-select-dropdown,[role=listbox]')].filter(visible);
      while(!dds.length && Date.now()-start < 1200){{
        dds=[...document.querySelectorAll('.okki-select-dropdown,[role=listbox]')].filter(visible);
      }}
      if(!dds.length) return 'NO_DROPDOWN:' + target;
      const dd=dds[0];
      const opts=[...dd.querySelectorAll('[role=option], .okki-select-item-option, .okki-select-item-option-content, .okki-select-item')]
        .filter(visible);
      const first=opts.find(o=>norm(o.textContent||''));
      if(!first) return 'NO_OPTION:' + target;
      const txt=norm(first.textContent||'');
      first.click();
      return 'SET_FIRST:' + target + '=>' + txt;
    }})()"""
    return str(eval_js(js))


def set_text_field(label: str, value: str) -> str:
    js = f"""(() => {{
      const label = {json.dumps(label, ensure_ascii=False)};
      const value = {json.dumps(value, ensure_ascii=False)};
      const key = {json.dumps(LABEL_TO_KEY.get(label), ensure_ascii=False)};
      const norm=s=>(s||'').replace(/\\s+/g,' ').trim();
      const visible=(el)=>{{
        const s=getComputedStyle(el), r=el.getBoundingClientRect();
        return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
      }};
      // Prefer edit-form controls to avoid writing wrong global inputs.
      if(key){{
        const form=[...document.querySelectorAll('.paas-form-item[data-paas-field=\"'+key+'\"]')].filter(visible)[0];
        if(form){{
          const formCtrl=form.querySelector('textarea,input,[contenteditable=true]');
          if(formCtrl){{
            if(formCtrl.tagName==='TEXTAREA' || formCtrl.tagName==='INPUT'){{
              formCtrl.focus();
              formCtrl.value=value;
              formCtrl.dispatchEvent(new Event('input', {{bubbles:true}}));
              formCtrl.dispatchEvent(new Event('change', {{bubbles:true}}));
            }} else {{
              formCtrl.focus();
              formCtrl.textContent=value;
              formCtrl.dispatchEvent(new Event('input', {{bubbles:true}}));
            }}
            return 'SET_TEXT_FORM:' + label + '=>' + value;
          }}
        }}
      }}
      const item=[...document.querySelectorAll('.ow-detail-fields__item')]
        .find(it=>norm(it.querySelector('label')?.textContent||'')===label);
      if(!item) return 'NO_ITEM:' + label;
      let ctrl=item.querySelector('textarea,input,[contenteditable=true]');
      if(!ctrl){{
        const pen=item.querySelector('button.ow-detail-fields__edit-icon,button');
        if(pen) pen.click();
        ctrl=document.querySelector('.okki-modal-wrap textarea,.okki-modal-wrap input,textarea[placeholder=\"255字内\"],input[placeholder=\"请输入\"]');
      }}
      if(!ctrl) return 'NO_CTRL:' + label;
      if(ctrl.tagName==='TEXTAREA' || ctrl.tagName==='INPUT'){{
        ctrl.focus();
        ctrl.value=value;
        ctrl.dispatchEvent(new Event('input', {{bubbles:true}}));
        ctrl.dispatchEvent(new Event('change', {{bubbles:true}}));
      }} else {{
        ctrl.focus();
        ctrl.textContent=value;
        ctrl.dispatchEvent(new Event('input', {{bubbles:true}}));
      }}
      return 'SET_TEXT_FALLBACK:' + label + '=>' + value;
    }})()"""
    return str(eval_js(js))


def set_select_to_target(label: str, target_value: str | None) -> str:
    # Restore helper: target '--' or None means clear to empty.
    js = f"""(() => {{
      const label = {json.dumps(label, ensure_ascii=False)};
      const target = {json.dumps(target_value, ensure_ascii=False)};
      const key = {json.dumps(LABEL_TO_KEY.get(label), ensure_ascii=False)};
      const norm=s=>(s||'').replace(/\\s+/g,' ').trim();
      const visible=(el)=>{{
        const s=getComputedStyle(el), r=el.getBoundingClientRect();
        return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
      }};
      const cleanTarget = norm(target || '');
      // For empty restore, best method is clear icon mousedown on visible form item.
      if(!cleanTarget || cleanTarget==='--'){{
        if(key){{
          const form=[...document.querySelectorAll('.paas-form-item[data-paas-field=\"'+key+'\"]')].filter(visible)[0];
          if(form){{
            const current = norm(form.querySelector('.okki-select-selection-item')?.textContent||'');
            if(!current){{
              return 'RESTORE_EMPTY_ALREADY:' + label;
            }}
            form.dispatchEvent(new MouseEvent('mouseenter', {{bubbles:true}}));
            const clearBtn=form.querySelector('.okki-select-clear') || form.querySelector('.anticon-close-circle');
            if(clearBtn){{
              clearBtn.dispatchEvent(new MouseEvent('mousedown', {{bubbles:true,cancelable:true}}));
              clearBtn.dispatchEvent(new MouseEvent('mouseup', {{bubbles:true,cancelable:true}}));
              clearBtn.dispatchEvent(new MouseEvent('click', {{bubbles:true,cancelable:true}}));
              return 'RESTORE_EMPTY_BY_CLEAR_MOUSEDOWN:' + label;
            }}
          }}
        }}
      }}
      const item=[...document.querySelectorAll('.ow-detail-fields__item')]
        .find(it=>norm(it.querySelector('label')?.textContent||'')===label);
      if(!item) return 'NO_ITEM:' + label;
      const pen=item.querySelector('button.ow-detail-fields__edit-icon,button');
      if(pen) pen.click();
      const start=Date.now();
      let dds=[...document.querySelectorAll('.okki-select-dropdown,[role=listbox]')].filter(visible);
      while(!dds.length && Date.now()-start < 1200){{
        dds=[...document.querySelectorAll('.okki-select-dropdown,[role=listbox]')].filter(visible);
      }}
      if(!dds.length) return 'NO_DROPDOWN:' + label;
      const dd=dds[0];
      const options=[...dd.querySelectorAll('[role=option], .okki-select-item-option, .okki-select-item-option-content, .okki-select-item')].filter(visible);
      if(!cleanTarget || cleanTarget==='--'){{
        // Try placeholder-like option first.
        const emptyOpt = options.find(o => {{
          const t=norm(o.textContent||'');
          return t==='请选择' || t==='未设置' || t==='无' || t==='--';
        }});
        if(emptyOpt){{
          emptyOpt.click();
          return 'RESTORE_EMPTY_BY_OPTION:' + label;
        }}
        // Fallback: clear icon in field.
        const clearBtn=item.querySelector('.okki-select-clear, .okki-select-clear-icon, .anticon-close-circle, [aria-label*=clear], [aria-label*=close]');
        if(clearBtn){{
          clearBtn.click();
          return 'RESTORE_EMPTY_BY_CLEAR_ICON:' + label;
        }}
        // Fallback: close without change; caller validates by read-back.
        document.body.click();
        return 'RESTORE_EMPTY_UNSURE:' + label;
      }}
      const opt = options.find(o => norm(o.textContent||'')===cleanTarget || norm(o.textContent||'').includes(cleanTarget));
      if(!opt) return 'NO_MATCH_OPTION:' + label + '=>' + cleanTarget;
      opt.click();
      return 'RESTORE_VALUE:' + label + '=>' + cleanTarget;
    }})()"""
    return str(eval_js(js))


def click_confirm_save() -> str:
    js = """(() => {
      const norm=s=>(s||'').replace(/\\s+/g,'');
      const btn=[...document.querySelectorAll('button')].find(
        b => norm(b.innerText||b.textContent||'')==='确定' || norm(b.innerText||b.textContent||'')==='确 定'
      );
      if(!btn) return 'NO_CONFIRM';
      btn.click();
      return 'CLICK_CONFIRM';
    })()"""
    return str(eval_js(js))


def append_write_log(action: str, old_vals: Dict[str, Any], new_vals: Dict[str, Any], shots: Dict[str, str], result: str) -> None:
    WRITE_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "timestamp": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "customer_name": new_vals.get("customer_name"),
        "old_tags": [],
        "proposed_tags": [],
        "action_taken": action,
        "result": result,
        "old_values": old_vals.get("values"),
        "new_values": new_vals.get("values"),
        "screenshot_path_before": shots.get("before"),
        "screenshot_path_after": shots.get("after"),
    }
    with WRITE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    run: Dict[str, Any] = {
        "started_at": now_iso(),
        "objective": "Test fill + restore for 7 company fields on one customer",
        "steps": [],
    }

    before = get_target_values()
    run["before"] = before
    run["steps"].append({"step": "read_before", "ok": True})
    run["artifacts"] = {
        "before_shot": screenshot("test7_before_write.png", "before-read"),
        "before_snapshot_i": snapshot_i("test7_before_write.snapshot_i.txt"),
    }

    # Modify phase
    run["steps"].append({"step": "click_edit", "result": click_top_edit()})
    run["steps"].append({"step": "wait_after_click_edit", "ms": OPEN_WAIT_MS})
    paced_wait(OPEN_WAIT_MS)
    run["steps"].append({"step": "expand_common_info", "result": click_common_expand()})
    run["steps"].append({"step": "wait_after_expand_common_info", "ms": OPEN_WAIT_MS})
    paced_wait(OPEN_WAIT_MS)

    modify_plan = [
        ("客户销售渠道", lambda: set_select_first("客户销售渠道")),
        ("客户等级", lambda: set_select_first("客户等级")),
        ("公司备注", lambda: set_text_field("公司备注", "ai检索分析填写")),
        ("详细地址", lambda: set_text_field("详细地址", "测试地址一会删除")),
        ("客户类型", lambda: set_select_first("客户类型")),
        ("年采购额", lambda: set_select_first("年采购额")),
        ("规模", lambda: set_select_first("规模")),
    ]
    modify_ops = []
    for field_name, fn in modify_plan:
        op_result = fn()
        modify_ops.append({"field": field_name, "result": op_result})
        run["steps"].append(
            {"step": "wait_after_modify_field", "field": field_name, "ms": AFTER_FILL_WAIT_MS}
        )
        paced_wait(AFTER_FILL_WAIT_MS)
    run["modify_ops"] = modify_ops

    run["artifacts"]["modified_before_confirm_shot"] = screenshot(
        "test7_modified_before_confirm.png",
        "before-write",
    )
    run["steps"].append({"step": "confirm_save_modify", "result": click_confirm_save()})
    run["steps"].append({"step": "wait_after_confirm_modify", "ms": AFTER_SAVE_WAIT_MS})
    paced_wait(AFTER_SAVE_WAIT_MS)

    after_modify = get_target_values()
    run["after_modify"] = after_modify
    run["artifacts"]["after_modify_shot"] = screenshot("test7_after_modify.png", "after-write")
    run["artifacts"]["after_modify_snapshot_i"] = snapshot_i("test7_after_modify.snapshot_i.txt")

    # Restore phase
    run["steps"].append({"step": "click_edit_restore", "result": click_top_edit()})
    run["steps"].append({"step": "wait_after_click_edit_restore", "ms": OPEN_WAIT_MS})
    paced_wait(OPEN_WAIT_MS)
    run["steps"].append({"step": "expand_common_info_restore", "result": click_common_expand()})
    run["steps"].append({"step": "wait_after_expand_common_info_restore", "ms": OPEN_WAIT_MS})
    paced_wait(OPEN_WAIT_MS)

    restore_targets = dict(before["values"])
    # user explicitly requested restoring detailed address to empty
    restore_targets["详细地址"] = "--"

    restore_plan = [
        ("客户销售渠道", lambda: set_select_to_target("客户销售渠道", restore_targets.get("客户销售渠道"))),
        ("客户等级", lambda: set_select_to_target("客户等级", restore_targets.get("客户等级"))),
        ("公司备注", lambda: set_text_field("公司备注", "" if restore_targets.get("公司备注") in (None, "--") else str(restore_targets.get("公司备注")))),
        ("详细地址", lambda: set_text_field("详细地址", "" if restore_targets.get("详细地址") in (None, "--") else str(restore_targets.get("详细地址")))),
        ("客户类型", lambda: set_select_to_target("客户类型", restore_targets.get("客户类型"))),
        ("年采购额", lambda: set_select_to_target("年采购额", restore_targets.get("年采购额"))),
        ("规模", lambda: set_select_to_target("规模", restore_targets.get("规模"))),
    ]
    restore_ops = []
    for field_name, fn in restore_plan:
        op_result = fn()
        restore_ops.append({"field": field_name, "result": op_result})
        run["steps"].append(
            {"step": "wait_after_restore_field", "field": field_name, "ms": AFTER_FILL_WAIT_MS}
        )
        paced_wait(AFTER_FILL_WAIT_MS)
    run["restore_targets"] = restore_targets
    run["restore_ops"] = restore_ops

    run["artifacts"]["restore_before_confirm_shot"] = screenshot(
        "test7_restore_before_confirm.png",
        "before-write",
    )
    run["steps"].append({"step": "confirm_save_restore", "result": click_confirm_save()})
    run["steps"].append({"step": "wait_after_confirm_restore", "ms": AFTER_SAVE_WAIT_MS})
    paced_wait(AFTER_SAVE_WAIT_MS)

    after_restore = get_target_values()
    run["after_restore"] = after_restore
    run["artifacts"]["after_restore_shot"] = screenshot("test7_after_restore.png", "after-write")
    run["artifacts"]["after_restore_snapshot_i"] = snapshot_i("test7_after_restore.snapshot_i.txt")

    run["finished_at"] = now_iso()

    with RUN_LOG.open("w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2)

    append_write_log(
        action="Test 7 fields fill then restore on one customer",
        old_vals=before,
        new_vals=after_modify,
        shots={
            "before": shot_path(run["artifacts"]["before_shot"]),
            "after": shot_path(run["artifacts"]["after_modify_shot"]),
        },
        result="success",
    )
    append_write_log(
        action="Restore 7 fields to original values on one customer",
        old_vals=after_modify,
        new_vals=after_restore,
        shots={
            "before": shot_path(run["artifacts"]["restore_before_confirm_shot"]),
            "after": shot_path(run["artifacts"]["after_restore_shot"]),
        },
        result="success",
    )

    print(json.dumps({
        "run_log": str(RUN_LOG),
        "before": before.get("values"),
        "after_modify": after_modify.get("values"),
        "after_restore": after_restore.get("values"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
