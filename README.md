# okki-analyse

This repository is moving from a browser-owning OKKI automation project toward a
platform spine that can be called by the Windows-side `kka` Companion and the
upstream business brain.

## Current Role

- `sys`: OKKI / Alibaba spine layer
- primary strength today: OKKI read, prepare, verify, audit
- long-term boundary: consume Playwright/browser-use observations, not own the browser

## Key Docs

- [sys_playwright_spine_refactor.md](docs/sys_playwright_spine_refactor.md)
- [okki_page_models.md](docs/okki_page_models.md)
- [okki_action_catalog.md](docs/okki_action_catalog.md)
- [okki_section_solidification_plan.md](docs/okki_section_solidification_plan.md)
