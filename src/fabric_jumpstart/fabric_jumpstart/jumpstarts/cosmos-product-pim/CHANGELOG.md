# Version history

## Pre-Rayfin checkpoint - 2026-10-06

- Preserve v1/v1.1 and the accepted four-function v2 deployment unchanged.
- Freeze this development state before beginning an isolated Rayfin application.
- This is a work-in-progress checkpoint, not a tested release: local source and
	previously generated UDF artifacts differ. Do not deploy it blindly.
- Next scope: non-AI catalog browsing, editing, reviews, audit history and
	archive/restore. No additional GraphQL gateway or AI infrastructure.
- Rayfin requires its own branch, application directory and Fabric item names;
	no existing deployment is republished as part of this checkpoint.

## v2.1 AI proposals - Deferred, unreleased

- Approved scope: notebook-free interactive generation using Fabric-native AI,
	stored evidence/provenance, human approval/rejection and UI-facing reads.
- Local proposal lifecycle and UI-facing read code exists, but is not included in
	the accepted four-function deployment. Generated artifacts remain unchanged.
- Direct SQL AI calls succeeded; the UDF connection probe failed because endpoint
	type `MirroredWarehouse` was unsupported. No UDF AI latency measured.
- User deferred AI enrichment. Preserve experiments without including them in the
	Rayfin deployable package. Non-AI UI work is now the next phase.

## v2.0 live single-user acceptance - 2026-10-06

User-provided setup-notebook output supersedes the pending-runtime status in the
historical deployment record below. It is not an agent-run acceptance test.

- Seed created three products; the second seed skipped all three.
- Bike update advanced version 1 to 2 once; replay returned the same event/version.
- Changed request under the same operation ID and stale version were rejected.
- Paginated history contained one matching update event with the expected diff,
	verified caller identity, invocation ID and `ttl: -1`.
- Operation: `912a4626-34f5-4e0e-b9b1-34c644115018`.
- Audit timestamp: `2026-10-06T15:12:06.685114Z`.
- Invocation: `95a5fba1-aa99-4f55-bffb-4a270b65c4e5`.
- Final notebook result: `PASS: seed, update, replay, conflicts and paged audit history`.
- **Not run:** denied second caller, granted second caller, simultaneous writes,
	lost-response fault injection, AI generation/approval/rejection and latency.
- **Pending:** partition/retention review and removal of temporary seed privilege.
	This is not full security/concurrency acceptance or readiness for the AI UI.

## v2.0 backend milestone 2 - 2026-10-06 - Unreleased

Local installation packaging added; Fabric items deployed, publication and
functional acceptance pending.

- Registered unlisted local Jumpstart `cosmos-product-pim`, ID 33.
- Added `ProductPimBackend.UserDataFunction` with a deterministic private backend
	wheel, four functions, verified-context and Cosmos connection binding metadata.
- Pinned Fabric UDF runtime 1.0 and Azure Cosmos SDK 4.16.4.
- Added explicit `principal_grants` installation option for opted-in scenarios.
	Grants are validated before provisioning and injected into the staged source;
	existing Jumpstarts retain their original behavior.
- Added `00_ProductPimSetup` for UDF-only seed/read/update/replay/conflict/history
	acceptance, with additional two-caller and concurrency checks documented.
- Added tests for private-wheel import, artifact freshness, grants, registry and
	two consecutive setup-notebook runs through the backend contract.
- Local PyPI SDK inspection was blocked by a package-CDN TLS handshake failure;
	no certificate checks were disabled and no live SDK verification is claimed.

This is backend-only packaging, not a release or AI/Rayfin implementation.
Stable v1 files and references remain unchanged.

### Live deployment record

- Date: 2026-10-06; workspace: ADI Osmos Challenge,
	`d0708f52-ffc4-4d3e-9fab-6e85dd3618fc`; capacity assigned and API access verified.
- User approved prefix `PIMv2_` and grants for their signed-in identity only.
- Deployed with the public `jumpstart.install("cosmos-product-pim", ...)` API,
	local bundled source, and no `update_existing` flag.
- Cosmos database: `PIMv2_CosmosProductPim`,
	`62bd3d60-1336-40f0-a051-6a63929974d4`.
- Automatically created SQL endpoint: `b5f4c95e-ac7a-4aa2-9783-005c45390a57`.
- UDF: `PIMv2_ProductPimBackend`, `758636a3-bb2b-4071-bdc8-ba739e611efd`.
- Notebook: `PIMv2_00_ProductPimSetup`, `21e32944-d29d-4447-ac12-40e7d81f016c`.
- Backend grants: tenant `72f988bf-86f1-41af-91ab-2d7cd011db47`,
	user object `bd801010-8a65-4c02-ab21-e6586edea69e`, roles `read`, `write`, `seed`.
	Remove `seed` and redeploy after initialization. No workspace sharing changed.
- Readback verified four function declarations, exact private-wheel bytes,
	dependency versions, approved grants, and resolved endpoint/database placeholders.
- Portal publication is not verified: the integrated browser requires sign-in.
	No notebook/seed/mutation was run; runtime, identity, concurrency and audit
	acceptance are still pending. This record does not claim production readiness.
- Validation: 43 v2 tests passed; 77 focused v2/installer/v1 regression tests and
	40 registry tests passed. Full Python suite: 209 passed, 1 failed in the unrelated
	Cosmos pipeline manifest test because an existing notebook `__pycache__` file
	was present. That scenario was not changed. Focused Ruff and ty checks passed;
	touched Python files have no editor diagnostics.

## v2.0 backend milestone 1 - 2026-10-06 - Unreleased

Separate scenario identity: `cosmos-product-pim`. Local source prototype only;
not yet registered, packaged, deployed or accepted in Fabric.

Added:
- Product-centered `/productId` model in a separate database/container.
- Product, review, audit-event and operation-receipt contracts; planned AI proposal contract.
- Fabric-context-derived actor, server-owned deny-by-default grants and no client actor field.
- Bounded field edits with server-generated diffs, expectedVersion and ETag checks.
- Atomic product patch, audit creation and persisted idempotency receipt.
- Authorized reads, paginated per-product history, soft deletion and restoration.
- Deterministic synthetic seed that preserves existing products.
- Local transaction/adapter tests and explicit live-validation release gates.

Differences from v1.1:
- Immutable product partition replaces mutable category partitioning.
- Trusted tenant/object identity replaces caller-supplied requestedBy.
- General auditEvent documents replace price-only priceChange documents.
- Durable operation fingerprints add retry deduplication.
- Money is represented in minor units; price mutation is not ported in milestone 1.
- No migration or overwrite of v1 data; no UI or AI generation in this milestone.

Next: publication/setup packaging, Fabric acceptance, then native AI proposal
generation and approval. Rayfin waits for backend readiness. Power BI remains
deferred. v2.1 semantic discovery and v2.2 conversational shopping are roadmap,
not implemented capabilities.

## v1.1 - Stable baseline (unchanged)

Commit: `95c6cf12adb2aaf9064ec103d3ad96fad393e7ea`.
Scenario: `cosmos-catalog-translytical`.

120 deterministic products, six categories, seeded price audits, category-filtered
bulk selection and percentage changes (up to 25 products), audit-history views.
Existing PriceWriteback UDF unchanged. Power BI deferred.

## v1.0 - Stable baseline (unchanged)

Commit: `1a496312061d7c7f790e5f88c463163c46a08111`.
Initial Cosmos catalog price-writeback scenario with provisioning, setup notebook,
validated UDF price changes and atomic price audit records.