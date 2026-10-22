# Cosmos Product PIM — Rayfin

Local implementation of an authenticated Fabric-only catalog application.
No deployment or remote resource creation is part of local preparation or tests.
**Hosted authentication, backend permissions, persistence, and actual index usage
remain pending live acceptance.** Historical checks against another deployment
are not evidence for this configuration.

## Features and consistency

- **Browse catalog / refresh** reads authoritative `list_products` pages without
  requiring search, embeddings, or a populated search index. Load subsequent pages
  using the returned product-ID cursor. Paging is not a transactional snapshot:
  refresh from the beginning to see products inserted before the cursor.
  The UI requests 20 products per page; full backend documents are parsed within
  an explicit 2 MiB response bound, then projected to approved display fields.
- Creation calls `create_product` once with a UUID operation ID, reason and
  product details. The backend atomically creates the product, audit event and
  idempotency receipt. Initial commercial values are `priceMinor: 0`,
  `currency: USD`; this UI cannot edit them.
- Editing, archive/restore and paginated audit history use the same authoritative
  backend. Successful mutation receipts verify only that mutation, not permissions
  for other accounts. Search freshness is independent of a successful write.
  The mutation's `indexingPending: true` is a hint, not a live index comparison;
  `get_search_index_status` provides the separate point-in-time check.
- Unknown create/update outcomes retain the original payload and operation ID in
  browser session storage solely for retry safety, not as a product database.
  Retry that exact operation; do not start another to resolve an uncertain outcome.
  Keep the browser session until resolution. Definitive conflicts are shown;
  version conflicts require reloading and reviewing the product.
- `get_search_index_status` compares authoritative and search versions for each
  visible catalog page. Missing/failed freshness checks show **not verified**,
  never “current”. Pending records remain browsable and editable.
- Name search accepts product-name text. Semantic search accepts only the three
  allowlisted, named, pre-embedded presets (`lightweight-shelter`,
  `cycling-safety`, `trail-riding`). There is **no online arbitrary semantic text**
  or separately provisioned model endpoint.
- Both search bridges hydrate ranked IDs, then exclude version/status mismatches,
  including races after backend ranking. They combine backend and bridge stale
  counts and show pending indexing. Results are point-in-time reads, not a
  guarantee against later changes; selecting a result reads it again.
- DiskANN is **configured**, not proven executed. Cosmos needs at least 1,000
  inserted vectors to use DiskANN; a three-vector demo falls back to a scan.
  Dataset size alone does not prove execution. Backend diagnostics and notebook
  relevance acceptance must be checked live. Bridge elapsed milliseconds include
  hydration/network work and are **not Cosmos query latency**.

The accompanying Python workflow implements `02_ProductPimReindex` as a polling
worker: it scans pending source versions, embeds only pending products with Fabric
AI, and defers conflicting updates to the next run. `01_ProductPimHybridSearch`
seeds 1,200 deterministic synthetic products, invokes the worker, and compares
keyword/vector/hybrid results across all three presets with a precision@5
acceptance threshold of 0.8. These are implemented notebook workflows, **not
locally proven live results**. No live worker schedule is enabled. The Rayfin app
does not trigger notebooks or create an external embedding service.

## Explicit portable configuration

No workspace, item, app endpoint or allowed account has a source-code default.
The functions runtime requires these environment settings:

| Setting | Value |
| --- | --- |
| `PIM_WORKSPACE_ID` | Existing authoritative backend workspace UUID |
| `PIM_UDF_ITEM_ID` | Existing PIM UDF item UUID |
| `PIM_RAYFIN_ENDPOINT` | Exact HTTPS Rayfin AppBackend endpoint (no query/fragment) |
| `PIM_CALLER_TENANT_ID` | Approved caller tenant UUID |
| `PIM_CALLER_AUDIENCE` | Exact signed caller-token audience UUID |
| `PIM_CALLER_SUBJECT` | Exact verified app/account subject, including workspace/project/user |

Obtain the endpoint and signed-account policy from the approved deployment;
do not guess or decode an unverified token as proof of identity. Configuration
validation pins the Fabric host/path, exact app subject, issuer, tenant and
audience, and fails closed if any setting is absent or inconsistent. The backend
and app may occupy different workspaces.

For a local Functions host, supply these as environment settings (or local
`Values` settings supported by that host). Never commit `local.settings.json`,
tokens or credentials. `configuration.example.json` documents placeholder names
only and is not loaded automatically.

Frontend local settings are `VITE_RAYFIN_API_URL`, `VITE_RAYFIN_PUBLISHABLE_KEY`
and, where required by runtime discovery, `VITE_FABRIC_WORKSPACE_ID`,
`VITE_FABRIC_ITEM_ID`, `VITE_FABRIC_PORTAL_URL`. Use the approved existing app's
public configuration in ignored `.env.local`; never put owner tokens there.
Hosted builds retain Rayfin dynamic runtime configuration.

`rayfin/rayfin.yml` preserves protected assets, Fabric authentication, and disabled
password authentication. Its redirect allowlist contains only local development
origins. Any future hosted redirect requires explicit target-specific review.

## Local preparation and validation

Use existing installed dependencies. If missing, restore from this npm workspace
root using the repository's approved install workflow.

```powershell
npm run prepare:local
npm run typecheck
npm run build
npm run lint
npm test
npm run validate:functions
npm run dev:frontend
```

`prepare:local` uses the installed Rayfin CLI's local TypeScript parser to generate
`packages/functions/src/types.ts` and runtime metadata from authored registrations.
It does not deploy, authenticate, invoke a service, obtain tokens or start a host.
This repository wrapper uses a version-specific internal generator, not a claimed
public CLI command; revalidate it when updating Rayfin. Do not hand-edit generated
function contracts or cast around the typed Functions client.

`dev:frontend` starts Vite only. Without approved backend/auth configuration the
existing authentication gate remains closed; no preview bypass is provided.
Do **not** run `npm run dev`, `rayfin up`, or deployment commands for local-only
validation: those workflows may provision or modify remote resources.

### Local validation status — 2026-10-20

| Command | Result |
| --- | --- |
| `npm run prepare:local` | Passed; local contracts generated, no deployment |
| `npm run typecheck` | Passed |
| `npm run build` | Passed |
| `npm run lint` | Passed |
| `npm test` | Passed: 36 bridge tests and 73 frontend tests |
| `npm run -w @rayfin-app/functions test` (integration follow-up) | Passed: 38 bridge tests, including >64 KiB catalog pages, 2 MiB rejection, and missing/null versus explicit-zero telemetry |
| `npm run validate:functions` | Passed: 9 authored/generated functions, no unsafe client casts |
| `git diff --check -- .` (from this app directory) | Passed |

These checks used existing installed dependencies and mocked backend responses.
No remote resource was created or changed; hosted-browser and live persistence
acceptance were not run.

## Trust and live limitations

Every bridge verifies the signed caller before accessing `ctx.Tokens.Fabric`:
RS256 signature, expiry, not-before, issuer, audience, tenant, exact subject and
runtime endpoint. The owner token stays server-side. Rayfin downstream operations
use the **app owner's identity**, not delegated multiuser identity. Do not broaden
the approved single-account policy to imply per-user backend authorization.

Connection checks make real authoritative-list and preset-search read requests.
They report passed, pending or failed independently; a ranking label is never
proof of index usage. Writes remain **configured-not-verified** until an actual
successful mutation in the current UI session. Local tests mock backend
contracts and do not establish hosted sign-in, external-token availability,
live grants, atomic storage behavior, relevance, RU charge or index execution.
Those require a separately approved live acceptance run.
