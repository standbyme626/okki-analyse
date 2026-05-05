# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

OKKI CRM (crm.xiaoman.cn) browser automation for customer tagging. Python scripts drive browser interactions through `agent-browser` CLI. See `AGENTS.md` for full safety rules and workflow conventions.

## Browser connection (critical)

All browser access goes through a **Windows Edge instance** that the user logs into manually. The Edge exposes CDP through a bridge running on the Windows host.

```
WSL (this repo) ──HTTP──▶ 172.22.208.1:21002 (bridge) ──▶ Edge CDP (Windows)
```

The bridge URL is auto-discovered by `okki_agent/edge_bridge.py` via `GET /json/version`. Override default with envar `OKKI_BRIDGE_URL`. The Edge must be launched on the Windows side first via `okki_edge_cdp_bridge.ps1`.

**Never use `agent-browser --session okki`** — that spawns a headless Chrome with no OKKI auth and all operations fail. All browser commands go through `--cdp <ws_url>` via `edge_bridge._run()`.

## Architecture

```
okki_agent/
  edge_bridge.py    ← CDP bridge connection, _run / _eval, prev_page / next_page
  writer.py         ← _ab_run/_ab_eval delegated to edge_bridge above;
                      edit/save/cancel, set/clear select fields, read field values;
                      all writer functions default dry_run=True (safe)
  reader.py         ← Read-only field extractors from snapshot text;
                      never clicks/types/saves — pure parsing
  page_model.py     ← Data models: PageMode, ReadResult, ActionPlan, StructuredError;
                      page mode detection, tab/section state detection
  verifier.py       ← Post-write readback comparison (no browser actions)
  audit.py          ← Audit helpers

scripts/            ← Entry-point scripts; each either wraps agent-browser directly
                      or imports from okki_agent.writer
```

Key relationship: `writer._ab_run` and `writer._ab_eval` are imported from `edge_bridge._run` / `edge_bridge._eval`. The `**_kw` on those functions absorbs legacy `session=` keyword args, so all 16 writer business functions work without any call-site changes.

## Writing scripts that control the browser

```python
from okki_agent.edge_bridge import _run, _eval, next_page, prev_page

_run("open", "https://crm.xiaoman.cn/crm/customer/list?...")
snap = _run("snapshot", "-i")           # accessibility tree with refs
_ref = _eval("document.querySelector(...).click()")  # JS in browser
next_page()   # → (1, 2), polls until page changes
prev_page()   # → (2, 1), raises if on page 1
```

## Commit convention

Record every modification in `docs/CHANGELOG.md`. Commit message in English.
