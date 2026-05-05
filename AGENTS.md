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

1. Open page with `agent-browser --session okki --headed open <url>`.
2. Ask user to log in manually when needed.
3. Run `agent-browser --session okki snapshot -i`.
4. Use refs like `@e1`, `@e2` only after a fresh snapshot.
5. Re-run snapshot after every navigation or DOM change.
6. Save screenshots into `screenshots/`.
7. Generate code only after verifying the page flow.

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
