# `sys` Playwright Spine Refactor

## 1. Goal

This repository should no longer evolve as a browser-owning OKKI automation app.

Its target role is:

- `sys`: platform spine
- primary focus: OKKI domain read / prepare / verify / audit
- secondary focus: Alibaba read-only placeholder / plan placeholder
- not responsible for browser ownership, orchestration, or business-wide state

## 2. System Layering

The agreed system layering is:

```text
Windows Browser
  -> D:\kka
     - SidePanel UI
     - Windows Companion
     - current page context
     - human review entry
  -> Playwright MCP
     - primary execution layer
  -> browser-use
     - exploration / fallback layer

sys
  - OKKI / Alibaba spine adapters
  - read model generation
  - prepare plan generation
  - verify model
  - audit model

ai-sales-system-text
  - primary business brain
  - primary workflow / task state / review / execution center
  - primary database / evidence / AI assessment / dashboard system

EIH
  - external evidence / discovery / watch / enrichment
```

## 3. Responsibility Split

### 3.1 `D:\kka`

`D:\kka` remains the Windows-side interaction and control shell.

It owns:

- SidePanel UI
- Companion WebSocket server/client chain
- Playwright MCP lifecycle
- browser-use lifecycle
- browser session ownership
- screenshot / snapshot / trace artifacts on Windows
- human review and approval UI

It does **not** own:

- main business state
- CRM-like persistence
- final workflow orchestration
- OKKI / Alibaba domain semantics

### 3.2 `sys`

`sys` becomes the spine layer.

It owns:

- page/read models
- OKKI-specific extraction logic
- OKKI-specific prepare plans
- write verification logic
- audit event construction
- Alibaba read-only placeholder and future adapter boundary

It does **not** own:

- browser sessions
- Playwright MCP
- browser-use
- global task state
- global review / execution persistence
- AI strategy orchestration

### 3.3 `ai-sales-system-text`

`ai-sales-system-text` is the only business brain / process center.

It owns:

- `Customer`
- `TaskState`
- `EvidencePackage`
- `AIAssessment`
- `FollowupRecommendation`
- `ReviewAction`
- `ExecutionJob`
- `ExecutionResult`
- `SampleCase`
- `RagMemory`
- dashboard and management views

### 3.4 `EIH`

`EIH` stays as the external intelligence system.

It owns:

- discovery
- crawl
- extract
- watch
- external evidence production

It does **not** become a CRM or execution center.

## 4. Why `sys` Must Change

The current repository is heavily optimized for:

- `agent-browser`
- Edge CDP bridge
- snapshot text in the old `snapshot -i` shape
- direct execution helpers living next to domain logic

That is no longer the right long-term boundary.

The new Windows-side stack will own:

- Playwright MCP as the primary execution layer
- browser-use as the exploration layer

So `sys` must move from:

```text
browser-owning OKKI automation project
```

to:

```text
browser-independent platform spine
```

## 5. Driver Policy

### 5.1 Playwright MCP

Playwright MCP is the primary browser execution path.

Use it for:

- `snapshot`
- `screenshot`
- `tabs`
- `evaluate`
- `click`
- `type`
- `select`
- `wait`

### 5.2 browser-use

browser-use is the exploration / fallback path.

Use it only when:

- page structure is unknown
- Playwright locators fail repeatedly
- the page has drifted and needs exploration

Do **not** let browser-use replace the primary execution path.

### 5.3 Companion Control Rule

The Windows Companion in `D:\kka` is the only tool scheduler.

It must prevent:

- Playwright MCP and browser-use controlling the page at the same time
- stale element references crossing approval boundaries
- browser control moving into WSL

## 6. Target `sys` Shape

`sys` should evolve into:

```text
okki_agent/
  core_models.py
  core_service.py
  alibaba_adapter.py
  page_model.py
  reader.py
  writer.py
  verifier.py
  audit.py
  edge_bridge.py          # legacy
  detail_page.py          # transitional / optional raw parser
  list_page.py            # transitional / optional raw parser
```

### 6.1 `core_models.py`

New neutral models for:

- `ObservationBundle`
- `ReadModel`
- `ActionIntent`
- `PreparedActionPlan`

These models must be browser-independent.

### 6.2 `core_service.py`

New stable entry points for the brain / Companion boundary:

- `detect_okki_page_mode(bundle)`
- `observe_okki_customer(bundle)`
- `prepare_okki_action(intent, bundle)`
- `verify_okki_action(before_bundle, after_bundle, expected)`
- `build_okki_audit_event(...)`

### 6.3 `alibaba_adapter.py`

New read-only placeholder boundary for Alibaba:

- page kind detection
- inquiry observation summary
- plan placeholder generation

This phase must not perform send / save / reply actions.

## 7. Observation Bundle Contract

The Windows-side Companion should eventually send `sys` a normalized bundle:

```json
{
  "platform": "okki | alibaba | unknown",
  "source": "playwright_mcp | browser_use | companion",
  "url": "",
  "title": "",
  "page_text": "",
  "playwright_snapshot": "",
  "screenshot_paths": [],
  "raw_payloads": {
    "detail_scene_raw": {},
    "edit_scene_raw": {},
    "list_scene_raw": {}
  },
  "metadata": {},
  "collected_at": ""
}
```

Key rule:

- `sys` consumes this bundle
- `sys` does not own the browser that produced it

## 8. OKKI Refactor Policy

OKKI remains the first fully supported adapter.

The refactor direction is:

1. preserve the semantic logic already present in:
   - `page_model.py`
   - `reader.py`
   - `writer.py`
   - `verifier.py`
   - `audit.py`
2. stop extending `edge_bridge.py` as the long-term integration boundary
3. move raw browser acquisition out of `sys`
4. let `sys` focus on:
   - read models
   - prepare plans
   - verify results
   - audit records

## 9. Alibaba Strategy

Alibaba is required, but this phase only needs read-only and placeholder support.

Phase-one Alibaba support in `sys` should include:

- page kind detection
- right-panel-first observation summary
- left-panel inquiry summary
- risk / review-required hints
- placeholder plans for:
  - draft reply
  - sync to OKKI
  - add customer

Phase-one Alibaba support must not do:

- send reply
- save profile changes
- click final business buttons

## 10. Migration Phases

### Phase 1: spine contract extraction

- add neutral models
- add stable service facade
- keep legacy CDP path untouched

### Phase 2: OKKI adapter formalization

- make current OKKI logic callable as bundle-based services
- keep prepare / verify / audit strong

### Phase 3: Alibaba read-only placeholder

- add page-kind detection
- add observation summary
- add placeholder plans

### Phase 4: Companion integration

- consume Playwright MCP outputs from `D:\kka`
- consume browser-use fallback outputs from `D:\kka`
- keep browser ownership on Windows

### Phase 5: brain integration

- `sys` outputs feed `ai-sales-system-text`
- `EvidencePackage`, `ReviewAction`, and `ExecutionJob` become the main persistence path

## 11. What Must Stay Legacy

These parts should remain available but no longer define the future architecture:

- `edge_bridge.py`
- direct browser mutation helpers in `writer.py`
- ad-hoc batch scripts under `scripts/`

They are still useful for:

- regression checks
- reference behavior
- controlled transitional runs

They should not be the destination architecture.

## 12. Immediate Refactor Start

The first concrete refactor slice in this repository is:

1. add `core_models.py`
2. add `core_service.py`
3. add `alibaba_adapter.py`
4. export the new service boundary from `okki_agent`
5. keep all legacy entry points intact

That gives the rest of the system a stable `sys` spine boundary before real Playwright and browser-use orchestration is wired in from `D:\kka`.
