# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

OKKI CRM (crm.xiaoman.cn) browser automation for customer tagging. Python scripts drive browser interactions through `agent-browser` CLI.

## Browser connection (critical)

All browser access goes through a **Windows Edge instance** that the user logs into manually. The Edge exposes CDP through a bridge running on the Windows host.

```
WSL (this repo) ──HTTP──▶ 172.22.208.1:21002 (bridge) ──▶ Edge CDP (Windows)
```

The bridge URL is auto-discovered by `okki_agent/edge_bridge.py` via `GET /json/version`. Override default with envar `OKKI_BRIDGE_URL`. The Edge must be launched on the Windows side first via `okki_edge_cdp_bridge.ps1`.

**Never use `agent-browser --session okki`** — that spawns a headless Chrome with no OKKI auth and all operations fail. All browser commands go through `--cdp <ws_url>` via `edge_bridge._run()`.

## Safety rules

- Never click **Save / Submit / Send / Delete / Confirm** buttons during exploration unless explicitly asked.
- Never batch-update, delete, merge, or archive OKKI records unless explicitly asked.
- Never send emails, messages, inquiries, or WhatsApp messages.
- All writer functions default to **dry_run=True**. Real writes require the user to explicitly lift this.
- After every write action, perform **read-back verification** of changed fields.
- Every write action must produce a log entry: customer name, old tags, proposed tags, action taken, success/failure, screenshot path.

## Browser interaction rules

### Selector strategy

- **Never hardcode transient `@eXX` refs** in long-term scripts — they expire across snapshots.
- Use **semantic anchors first**: field labels (`客户等级`), section names (`公司常用信息`), stable text near the target.
- Fallback selectors only when semantic anchors fail. Never rely on screen coordinates.
- Keep a state-machine approach for list page vs detail page transitions.

### Snapshot discipline

- `snapshot -i` before any interaction to get fresh refs.
- Re-run snapshot after **every** navigation or DOM change.
- `@eXX` refs are valid only for the immediately following action, not beyond.

## Knowledge solidification workflow

After every script run or browser experiment, check whether the run produced reusable knowledge.

Solidify these findings when discovered:

- New OKKI interface endpoint
- Request parameters or payload schema
- Response fields
- Field mapping
- Stable UI selector strategy
- Page mode or state transition
- Failure mode and recovery rule

Where to record:

- `OKKI_INTERFACES.md` for confirmed endpoints, payloads, response fields, and risk notes.
- `RUN_REVIEW_AND_SOLIDIFICATION.md` for run-review and solidification rules.
- `CHANGELOG.md` for every repository file modification.
- `logs/experiment-runs.jsonl` for browser experiments.
- Code modules when the behavior is stable enough to reuse.

Interface path is the primary automation path. UI path is the fallback and verification path.

For UI automation, never preserve temporary `@eXX` refs as durable selectors. Use semantic anchors such as field labels, section titles, drawer/footer context, and page mode detection.

For write automation, do not submit partial payloads to full-form save endpoints. Read the original edit data first, construct a full payload, change only the target fields, verify the diff, write, then read back.

## Page modes

OKKI customer detail has two modes. Automation must **detect the current mode first**, then route to the matching action flow:

| Mode | How to reach | Detection |
|------|-------------|-----------|
| **Drawer** | Open detail in right-side panel from customer list | `"客户列表"` or tab markers in snapshot, no full-page URL |
| **Full-page** | Navigate to `/crm/customer/personal?company_id=...` | URL matches route, `"客户详情"` in title |

## Screenshot checkpoints

Don't screenshot every step. Only at these four checkpoints:

| Checkpoint | When |
|------------|------|
| `before-read` | Arrived on target customer detail |
| `before-write` | Just before any write-intent operation |
| `after-write` | After save/confirm (when explicitly allowed) |
| `on-error` | Any failed locator / action / validation |

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

## Confirmed OKKI interface notes

Confirmed interface notes live in `OKKI_INTERFACES.md`.

Current important findings:

- Stage 1 list read path: `POST /api/customerV3Read/companyList`
- Customer detail edit save path: `POST /api/customerV3Write/edit`
- Company remark field: `data.remark`
- Detail readback path: `GET /api/customerV2Read/detail?company_id=...&scene=detail`
- Edit raw data path: `GET /api/customerV2Read/detail?company_id=...&scene=edit`

The edit save endpoint is a full-form save endpoint, not a single-field patch endpoint.

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

- Record every modification in repository-root `CHANGELOG.md`.
- Every change entry must include: date, objective, touched files, and impact summary.
- Commit message in English.
