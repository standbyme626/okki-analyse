# OKKI Tagging Automation Project

## Goal

Build a safe browser automation workflow for OKKI customer tagging.

## Tools

Use `agent-browser` to inspect OKKI pages and test browser interactions.
Prefer generating Playwright or Browser Use scripts for repeatable execution.

## Safety Rules

- Do not batch update OKKI records unless explicitly asked.
- Do not send emails, messages, inquiries, or WhatsApp messages.
- Do not delete, merge, or archive customers.
- Do not click final "Save", "Submit", "Send", "Delete", or "Confirm" buttons during exploration unless explicitly asked.
- For login, ask the user to log in manually in the headed browser.
- Start with dry-run scripts that only read data and output proposed tags.
- Every write action must produce a log entry with customer name, old tags, proposed tags, action taken, success/failure, and screenshot path.

## Page Modes

- OKKI customer detail has two valid modes:
- Drawer mode: open detail in right-side panel from customer list page.
- Full-page mode: navigate to `/crm/customer/personal?company_id=...`.
- Automation must detect current mode first, then route to the matching action flow.

## Execution Policy

- During exploration, do read-only actions first: `get`, `snapshot`, `screenshot`, `find`, `eval` (read-only).
- Before any click in exploration, state which `ref` or selector will be clicked and why.
- Re-run `snapshot -i` after every navigation or DOM change.
- Never rely on coordinates for production logic.

## Selector Strategy

- Do not hardcode transient `@eXX` refs in long-term scripts.
- Use semantic anchors first (field labels like `客户等级`, section names like `资料`, stable text near target).
- Use fallback selectors only when semantic anchors fail.
- Keep a state-machine approach for list page vs detail page transitions.

## Screenshot Policy

- Screenshot is required at key checkpoints, not every single step.
- Required checkpoints:
- `before-read` (arrived on target customer detail)
- `before-write` (just before any write-intent operation)
- `after-write` (after save/confirm when explicitly allowed)
- `on-error` (any failed locator/action/validation)

## Experiment Log Standard

- Every experiment run must append a structured log record including:
- objective
- start_url
- page_mode (`drawer` or `full_page`)
- commands_executed
- clicked_target (ref/selector + reason)
- expected_result
- actual_result
- screenshot_paths
- conclusion

## Agent Browser Workflow

1. Ensure Windows Edge CDP bridge is running (`okki_edge_cdp_bridge.ps1`) and user is logged in manually in Edge.
2. Never use `agent-browser --session okki`.
3. Prefer `okki_agent.edge_bridge._run()` / `_eval()` for browser commands (auto-discovery from bridge `/json/version`).
4. If raw CLI is needed, use `agent-browser --cdp <ws_url> <command>`.
5. Run `snapshot -i` before interaction, and re-run after every navigation or DOM change.
6. Use refs like `@e1`, `@e2` only from the latest snapshot.
7. Save screenshots into `screenshots/`.
8. Generate code only after verifying the page flow.

## First MVP

Create a script that handles one test customer only:
1. Search customer
2. Open customer detail
3. Read existing tags
4. Propose tags
5. Stop before saving

## Write Guardrails

- Default `dry_run=True` for all writer functions.
- Single-customer write is allowed only when explicitly requested by user.
- Bulk writes are forbidden unless user explicitly approves batch scope and stop conditions.
- After a write, always perform read-back verification of changed fields.

## Run Review And Solidification

- After every script run, browser experiment, HAR capture, or UI probe, review whether new knowledge should be solidified.
- Interface solidification is the primary path for repeatable read/write automation.
- UI solidification is required as the fallback path and verification path.
- Do not keep newly discovered selectors, endpoints, payload fields, or failure modes only in chat history.
- If a run discovers reusable interface behavior, update `OKKI_INTERFACES.md`.
- If a run discovers reusable UI behavior, update UI model documentation or code.
- If a run changes files, update repository-root `CHANGELOG.md`.
- If a run involves browser experimentation, append `logs/experiment-runs.jsonl`.

## Interface And UI Solidification

- Read interfaces may be used for data collection and verification when they are observed from normal OKKI page behavior.
- Write interfaces must not be called unless the user explicitly approves the exact customer scope, fields, stop conditions, and verification plan.
- Known OKKI interfaces and field mappings are recorded in `OKKI_INTERFACES.md`.
- Known run-review rules are recorded in `RUN_REVIEW_AND_SOLIDIFICATION.md`.
- UI selectors must be semantic and reusable. Do not solidify temporary `@eXX` refs.
- Preferred UI field strategy: `label text -> form item/container -> input/textarea/select`.
- Preferred write safety strategy: read old value, build full payload, diff only target fields, write, read back, log result.

## Change Log Discipline

- Every repository modification must append one entry in `CHANGELOG.md`.
- Each entry should include: date, objective, changed files, and behavioral impact.
