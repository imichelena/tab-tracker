# Build Plan — Tab Tracker POS Extension

**Branch:** `feat/pos-extension`
**Spec:** `docs/SPEC.md`
**Pipeline:** PM → QA → Security → Documentation

---

## Pipeline Overview

```
Phase 0: Scaffold (this plan)
    ↓
Phase 1: PM Agent — break spec into tasks, assign priorities, define acceptance criteria
    ↓
Phase 2: Build (executed by delegated agents per PM's task breakdown)
    ↓
Phase 3: QA Agent — verify against test cases in spec §8.2
    ↓
Phase 4: Security Agent — audit auth chain, secrets, API endpoints
    ↓
Phase 5: Documentation Agent — README, API docs, deployment guide
```

---

## Phase 0: Scaffold (done before agents spawn)

### 0.1 Repo structure
```
tab-tracker/
├── docs/
│   ├── SPEC.md              ✅ Written
│   ├── BUILD_PLAN.md        ✅ This file
│   ├── PM_REPORT.md         ⬜ PM agent output
│   ├── QA_REPORT.md         ⬜ QA agent output
│   ├── SECURITY_REPORT.md   ⬜ Security agent output
│   └── DEPLOYMENT.md        ⬜ Docs agent output
├── extension/               ⬜ POS extension (Phase 2)
│   ├── shopify.extension.toml
│   ├── package.json
│   ├── src/
│   └── ...
├── migrations/
│   └── 002_pos_extension.sql  ⬜ DB migration
├── app.py                   ✅ Existing — add /api/v1/* endpoints
├── models.py                ✅ Existing — add pos_sessions model
├── shopify.py               ✅ Existing — keep draft order as fallback
├── templates/               ✅ Existing web UI (unchanged)
└── ...
```

### 0.2 Git
- Branch `feat/pos-extension` created from `main` ✅
- Commit spec + plan ✅
- Push to origin

---

## Phase 1: PM Agent

**Input:** `docs/SPEC.md`
**Output:** `docs/PM_REPORT.md`

### PM Agent Instructions

Read the spec at `docs/SPEC.md`. Break the build into ordered tasks with:

1. **Task ID** (T-01, T-02, ...)
2. **Task name**
3. **Description** (what to build, which files)
4. **Dependencies** (which tasks must complete first)
5. **Priority** (P0 = blocker, P1 = critical, P2 = important, P3 = nice-to-have)
6. **Estimated effort** (S/M/L)
7. **Acceptance criteria** (concrete, testable)
8. **Agent type** (which delegated agent should execute it)

### Expected Task Breakdown (PM should refine)

| ID | Task | Deps | Priority | Effort |
|---|---|---|---|---|
| T-01 | DB migration: pos_sessions table, tabs/transactions column additions | — | P0 | S |
| T-02 | Backend: `/api/v1/products` + `/api/v1/categories` endpoints | — | P0 | S |
| T-03 | Backend: `/api/v1/tables` + `/api/v1/tabs` CRUD endpoints | T-01 | P0 | M |
| T-04 | Backend: `/api/v1/tabs/{id}/send-to-cart` endpoint (transaction recording) | T-01, T-03 | P0 | S |
| T-05 | Backend: API key auth middleware for `/api/v1/*` | — | P0 | S |
| T-06 | Extension scaffold: shopify.extension.toml, package.json, vite config | — | P0 | S |
| T-07 | Extension: home tile + modal shell (pos.home.tile.render + pos.home.modal.render) | T-06 | P0 | S |
| T-08 | Extension: API client (fetch products, tabs from backend) | T-05, T-02 | P0 | S |
| T-09 | Extension: CategoryBar + ProductGrid components | T-08 | P0 | M |
| T-10 | Extension: TabBill + tab item management (add/remove/qty) | T-08, T-03 | P0 | M |
| T-11 | Extension: SendToCart — Cart API integration (addLineItem, addCustomSale, clearCart) | T-10, T-04 | P0 | L |
| T-12 | Extension: TabList view (multiple tables/tabs) | T-10 | P1 | M |
| T-13 | Extension: Error handling (backend down, cart API fail, retry logic) | T-11 | P1 | M |
| T-14 | Extension: Loading states + success/confirmation flows | T-11 | P1 | S |
| T-15 | Backend: transaction history endpoint `/api/v1/transactions` | T-04 | P2 | S |
| T-16 | Testing: dev store setup guide + test case checklist | T-11 | P1 | S |

---

## Phase 2: Build

Executed by delegated coding agents per PM's task breakdown.

### Execution Order (critical path)

```
T-01 ─┬─→ T-03 ──→ T-04
      │
T-02 ─┤
      │
T-05 ─┴─→ T-08 ──→ T-09
                ──→ T-10 ──→ T-11 ──→ T-13
                       │         │
                       ↓         ↓
                      T-12      T-14
                       
T-06 ──→ T-07 (independent of backend, can parallel)
```

### Parallel Workstreams

- **Workstream A (Backend):** T-01 → T-02 → T-03 → T-04 → T-05
- **Workstream B (Extension):** T-06 → T-07 (scaffold)
- **Workstream C (Extension UI):** T-08 → T-09 + T-10 → T-11 → T-12 + T-13 + T-14

A and B can run in parallel. C depends on A + B.

---

## Phase 3: QA Agent

**Input:** `docs/SPEC.md` (§8.2 test cases), `docs/PM_REPORT.md`, built extension + backend
**Output:** `docs/QA_REPORT.md`

### QA Agent Instructions

1. For each test case T01–T10 in the spec:
   - Describe exact steps to reproduce
   - Expected result (from spec)
   - Actual result (from testing or code review)
   - Pass/Fail status
   - If fail: root cause + recommended fix
2. Verify:
   - All P0 tasks have acceptance criteria met
   - No TypeScript errors in extension
   - No Python errors in backend
   - API endpoints respond with correct JSON
   - Cart API calls are correctly structured
3. Test edge cases:
   - Empty tab sent to cart
   - Tab with 20+ items
   - Rapid add/remove (race conditions)
   - Backend timeout during send-to-cart
4. Output structured report with pass/fail matrix

---

## Phase 4: Security Agent

**Input:** `docs/SPEC.md` (§7 security), backend code, extension code
**Output:** `docs/SECURITY_REPORT.md`

### Security Agent Instructions

1. **Authentication audit:**
   - Verify API key validation on all `/api/v1/*` endpoints
   - Verify Shopify session token handling
   - Check for unauthenticated endpoints
   - Verify no secrets in extension source code

2. **Input validation:**
   - SQL injection checks on all DB queries
   - XSS checks on any user-provided content
   - Input validation on POST/PATCH/DELETE bodies
   - Integer overflow / negative quantity checks

3. **Secrets audit:**
   - Grep extension code for hardcoded tokens/keys
   - Grep backend for hardcoded credentials (should be env vars)
   - Verify `.env` is in `.gitignore`
   - Verify `.env.example` has no real values

4. **Network security:**
   - Verify HTTPS enforcement
   - CORS policy review
   - Rate limiting verification

5. **Output:** Structured report with severity levels (Critical/High/Medium/Low) per finding

---

## Phase 5: Documentation Agent

**Input:** All prior docs + code
**Output:** `docs/DEPLOYMENT.md` + updated `README.md`

### Documentation Agent Instructions

1. **README.md** — Update with:
   - Architecture overview (with diagram)
   - Two modes: POS extension (primary) + web UI (admin/legacy)
   - Setup instructions (backend + extension)
   - Configuration reference (env vars)
   - Development workflow

2. **docs/DEPLOYMENT.md** — Create with:
   - Backend deployment (VPS, systemd, PostgreSQL)
   - Extension deployment (Shopify CLI, app setup)
   - Shopify Partner account setup steps
   - Dev store creation
   - POS device installation
   - Rollback procedure
   - DB migration steps

3. **docs/API.md** — Create with:
   - Full API reference for all `/api/v1/*` endpoints
   - Request/response examples
   - Authentication header format
   - Error response format

---

## File Checklist

| File | Phase | Status |
|---|---|---|
| `docs/SPEC.md` | 0 | ✅ |
| `docs/BUILD_PLAN.md` | 0 | ✅ |
| `docs/PM_REPORT.md` | 1 | ⬜ |
| `migrations/002_pos_extension.sql` | 2 | ⬜ |
| `extension/shopify.extension.toml` | 2 | ⬜ |
| `extension/src/index.tsx` | 2 | ⬜ |
| `extension/src/modal.tsx` | 2 | ⬜ |
| `extension/src/components/*.tsx` | 2 | ⬜ |
| `app.py` (new /api/v1/* endpoints) | 2 | ⬜ |
| `models.py` (pos_sessions model) | 2 | ⬜ |
| `docs/QA_REPORT.md` | 3 | ⬜ |
| `docs/SECURITY_REPORT.md` | 4 | ⬜ |
| `docs/DEPLOYMENT.md` | 5 | ⬜ |
| `README.md` (updated) | 5 | ⬜ |
| `docs/API.md` | 5 | ⬜ |

---

## Key Constraints

1. **Never break the existing web UI** — floor.html, admin.html, history.html must continue to work
2. **Draft order flow preserved** as fallback (`CHECKOUT_METHOD=draft_order`)
3. **Single shop pilot** — multi-shop comes later
4. **Custom app** — not App Store
5. **English only** — all docs and code comments in English
6. **Evidence-first** — every claim in QA/Security reports must cite specific code lines or test output
