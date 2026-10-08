# Cosmos Product PIM

Status: **v0.3.2 native hybrid/name-search backend and Rayfin demo; Fabric notebook acceptance required**.
Logical identity: `cosmos-product-pim`. No existing v1 scenario is modified.
This milestone adds Fabric-native product discovery to the audited PIM backend.
See [CHANGELOG.md](CHANGELOG.md) for the version-by-version record.

## Native hybrid search

The authoritative `ProductPim` container remains unchanged. Derived search
documents live in `ProductPimSearch`, which has a 1,536-dimensional `float32`
cosine vector policy, DiskANN index, and English full-text/BM25 index. The
`01_ProductPimHybridSearch` notebook uses Fabric `ai.embed` to index products and
three named demo intents, then verifies native Cosmos
`RRF(VectorDistance(...), FullTextScore(...))` ranking.

Rayfin accepts only those named query IDs. The UDF retrieves the corresponding
stored vector from the fixed `__search_queries__` partition, runs the hybrid
query, and returns ranked product IDs. The trusted Rayfin bridge then reads each
authoritative product before presenting it. This demonstrates real DiskANN,
BM25, and RRF without Azure AI Search, a separate Cosmos account, or an external
model endpoint. Arbitrary live semantic text is intentionally unsupported
because Fabric notebook AI Functions are not an interactive Rayfin endpoint.

The Rayfin editor also supports free-text product-name lookup. Search documents
carry the authoritative name snapshot created by the notebook. Cosmos applies a
case-insensitive name-term filter and ranks matches with the existing BM25
full-text index. Rayfin then reads the authoritative product by its internal ID;
the user never needs to enter that ID.

Deployment order:

1. Install or update the Jumpstart with `update_existing=True`.
2. Publish the corrected Product PIM UDF from `v0.3.2`.
3. Run `01_ProductPimHybridSearch` and confirm all product and query documents.
4. Deploy or update the Rayfin app and run each named search from the UI.

## Checkpoint boundary - 2026-10-06

This directory is preserved as the pre-Rayfin development checkpoint, not a new
release. The deployed v2 UDF and existing generated artifacts contain four
functions. Local source additionally contains catalog/review reads and unfinished
AI proposal generation/decision code; generated artifacts have not been rebuilt
from that source. Do not rebuild and publish this checkpoint over the accepted
deployment without resolving that difference.

AI enrichment is explicitly deferred. Direct SQL AI succeeded, but the tested UDF
managed connection rejected the Cosmos SQL endpoint type `MirroredWarehouse`.
There is no working UDF-to-SQL-AI integration or latency guarantee.

Rayfin development belongs on a separate branch and in a separate application
directory, with separately named Fabric development items. Existing v1 and v2
deployments must not be overwritten. The next scope is a non-AI catalog editor,
reviews, history and archive/restore. App-to-UDF identity propagation, second-caller
authorization, concurrency, lost-response handling and removal of seed privileges
remain acceptance gates. Later sections describing AI are historical design notes,
not active implementation scope.

## Scope and architecture

| Component | Responsibility | State |
| --- | --- | --- |
| Cosmos DB in Fabric | Authoritative products, reviews, proposals, audit events and retry receipts | Separate database deployed; single-user seed/read/write/history accepted |
| Fabric User Data Functions | Trusted caller identity, authorization, reads, validated atomic writes | Published runtime and private wheel exercised successfully by the user |
| Fabric AI Functions | Generate grounded suggestions using the built-in Fabric model endpoint | Planned; integration spike required |
| Fabric Apps / Rayfin | Governed product editing, audit history, and explained hybrid discovery | Implemented; deploy after notebook acceptance |
| Power BI | Analytics and audit reporting | Deferred |
| Cosmos vector/hybrid retrieval | DiskANN + BM25 fused with native RRF | Implemented in separate search container |
| Conversational shopping | Retrieval-grounded assistant | v2.2, deferred |

No separately provisioned Azure OpenAI, Foundry project, Azure Functions, external
model hosting, or model API key is required by this design. Cosmos stores and
retrieves information; it does not generate text. Fabric AI Functions performs
generation, while UDFs govern persistence and approval.

## Storage and identity

Use a **separate Cosmos DB in Fabric database**, proposed display name
`CosmosProductPim`, and container `ProductPim`, partitioned by `/productId`.
Never repoint v2 at the v1 `SampleData` container. Product IDs are immutable,
case-sensitive identifiers of 1-100 letters, digits, underscores or hyphens.
Categories are editable business attributes, not partition keys.

All documents for one product share its partition. Transactions are atomic per
product, not across the catalog. The provisioning definition enables TTL with a
default of `-1` (no expiration); audit and operation documents also specify `-1`.
Do not add expiration to these records without revisiting retention and retries.

| docType | ID pattern | Contract |
| --- | --- | --- |
| `product` | `product:<productId>` | Current state; schemaVersion, integer version, status, content, commercial and creation/update metadata |
| `review` | `review:<productId>:<reviewId>` | Rating, text, source and creation time; seed evidence is immutable through this API |
| `auditEvent` | `event:<operationId>` | Actor, action, before/after values, versions, reason, invocation and operation IDs, UTC timestamp |
| `operation` | `operation:<operationId>` | Canonical request/actor fingerprint and original committed result |
| `aiProposal` | `proposal:<proposalId>` | Planned: source product version, evidence, prompt, model, output and approval lifecycle |

Every document includes `productId` and `schemaVersion: 1`. Product shape:

```json
{
  "id": "product:bike-100",
  "docType": "product",
  "schemaVersion": 1,
  "productId": "bike-100",
  "version": 1,
  "status": "active",
  "name": "Trail bike",
  "categoryName": "Bikes",
  "description": "Aluminum frame with 21 gears.",
  "marketing": {"shortDescription": "", "seoKeywords": []},
  "commercial": {"priceMinor": 89999, "currency": "USD"},
  "createdAt": "2026-10-06T00:00:00Z",
  "createdBy": {"tenantId": "<verified-tenant-guid>", "oid": "<verified-object-guid>"},
  "updatedAt": "2026-10-06T00:00:00Z",
  "updatedBy": {"tenantId": "<verified-tenant-guid>", "oid": "<verified-object-guid>"}
}
```

`priceMinor` uses integer USD cents rather than binary floating-point money.
Additional currencies need explicit minor-unit rules. Commercial and marketing
fields are read-only in this first milestone; price editing remains a v1 feature.
Seed content is three deterministic synthetic products and two synthetic reviews
per product, not a fetched or attributed Microsoft customer-review dataset.
Seeding creates each product, its reviews and creation event in one batch. It
skips existing products entirely, never upserts or resets user changes.

## Caller and authorization contract

The Fabric adapter obtains `TenantId`, `Oid` and `invocation_id` exclusively from
`@udf.context(argName="myContext")`. The tenant/object pair identifies the caller;
`PreferredUsername`, when present, is only a readable snapshot. The caller can be
a user or service principal; the prototype does not guess which from a username.

`PRINCIPAL_GRANTS` is a server-owned, empty-by-default allowlist keyed by
`<tenant-guid>:<object-guid>` with independent `read`, `write` and `seed` grants.
The installer requires explicit `principal_grants` and injects them only into
the staged UDF source, leaving the checked-in default empty. Missing or invalid
grants fail validation before workspace provisioning. No
public function accepts grants, an actor, or connection credentials from clients.
Authorization runs before obtaining the database client. The bootstrap `seed`
grant must be restricted to operators and removed after initialization.

The generic Cosmos connection uses the **UDF owner's identity**, not necessarily
the invoking caller. End users must have invocation access without direct Cosmos
write access or UDF edit access. Workspace administrators/publishers remain trusted.
An on-behalf-of user must not be claimed when a service principal invokes the UDF.
Group-based authorization and per-product access control are not implemented.

## API and write guarantees

| Function | Client arguments | Grant |
| --- | --- | --- |
| `get_product` | `productId` | `read` |
| `get_history` | `productId`, `pageSize` (1-100), `continuationToken` (empty initially) | `read` |
| `update_product` | `payload` as below | `write` |
| `seed_catalog` | None | `seed` |

```json
{
  "productId": "bike-100",
  "expectedVersion": 1,
  "operationId": "33333333-3333-4333-8333-333333333333",
  "changes": {"categoryName": "Mountain Bikes", "description": "Approved factual description."},
  "reason": "Correct catalog content"
}
```

1. Validate the verified caller, authorization, exact request fields and sizes.
2. Check the persisted operation receipt before checking the current version.
3. Read the product; require matching expectedVersion and an ETag.
4. Compute old/new values on the server. Reject no-ops and unknown fields.
5. Submit one ETag-conditioned batch: patch product and increment version,
   create audit event, create operation receipt. Never update audit events.
6. Return the committed version/event ID. After a lost response, inspect the
   receipt; otherwise report an unknown outcome and retry with the same ID.

Allowed changes are `name` (200 chars), `description` (4000), `categoryName`
(100), and `status` (`active` or `deleted`). Reason is required, max 500 chars.
Text is trimmed before comparison/fingerprinting. Each operation ID is a UUID,
scoped to a product partition, and must remain stable across retries.
The SHA-256 fingerprint includes canonical normalized request data and tenant/object
IDs, but excludes the mutable username and invocation ID. Reusing a key with a
different payload or principal is rejected, not replayed. Receipts have no TTL.
Rejected attempts are not persisted as domain events in this milestone.

Soft deletion is a status-only change. Deleted products reject content edits;
restore with a status-only change back to `active`, creating a new version/event.
Historical-content restoration is not implemented yet and must create a new
audited version when added. There is no hard-delete or audit-edit API.
History is partition-scoped, newest first and continuation-paginated; responses
omit Cosmos internal metadata. Reads may reflect the configured Cosmos consistency
level; after a mutation, use its returned version when evaluating subsequent reads.

Audit history is **append-only through this application**, not tamper-proof
against privileged administrators. Compliance retention, backups, monitoring of
denied attempts, privacy/erasure requirements, and independent immutable archival
need an explicit policy. Latest-version change feed alone is not an audit ledger.

## AI proposal contract and planned lifecycle

Generation must create a pending proposal, never silently publish product content.
Planned proposal fields include: sourceProductVersion; evidence snapshots and IDs;
promptTemplateVersion, actual prompt and input snapshot; provider (`Fabric AI
Functions`), actual model when available; generated output; requester; UTC times;
status (`pending`, `approved`, `rejected`); decision actor and reason. Review text
is untrusted input, not instructions, and output must pass a strict field schema.

Proposal generation and rejection each create an audit event with unchanged product
version. Approval must check both product version and proposal ETag/status, then
atomically patch product, transition proposal, write audit and operation receipt.
Stale proposals must be regenerated/reviewed, not applied to a newer product.
Asynchronous jobs must record both the authenticated job principal and a link to
the original verified request event; do not fabricate the original user's identity.

The candidate UDF -> SQL analytics endpoint -> SQL AI Functions integration has
**not been verified** for this Cosmos endpoint. A Fabric notebook with native
pandas/PySpark AI Functions is the fallback, still persisting through governed UDF
contracts. Capacity, tenant/region enablement, execution limits and connection
permissions must be checked in the target environment. Do not treat SQL support
in an overview as proof of this complete route. Fabric AI Functions does not
automatically preserve application prompts, evidence and outputs; we must do so.

## Install from this checkout

This unlisted local entry uses ID 33 and the existing local-source installation
path. It is not available in the currently published PyPI release. Use this
checkout's Python environment (or a wheel built from this checkout), not a
previously installed release. It does not reference a v1 source commit.

```python
import fabric_jumpstart as jumpstart

jumpstart.install(
  "cosmos-product-pim",
  workspace_id="<target-workspace-guid>",
  item_prefix="PIMv2_",
  principal_grants={
    "<approved-tenant-guid>:<approved-user-object-guid>": ["read", "write", "seed"]
  },
)
```

Prerequisites: an active capacity-backed Fabric workspace, Cosmos DB in Fabric
and User Data Functions available in its region/tenant, and an authenticated
publisher with item creation and database write permissions. Fabric execution
permissions and backend grants are separate: installation configures the backend
allowlist, not workspace/item sharing. It never grants arbitrary workspace users
access or derives an audit actor from the installation options.

The payload creates `PIMv2_CosmosProductPim` with the authoritative `ProductPim`
container and derived `ProductPimSearch` container, `PIMv2_ProductPimBackend`,
`PIMv2_00_ProductPimSetup`, and `PIMv2_01_ProductPimHybridSearch`. Open the setup
notebook and follow its instructions. Neither notebook is auto-run. Publish in
Fabric if the UDF reports unpublished changes. The current test deployment passed
single-user runtime acceptance; every new installation still requires its own
acceptance.

To update an existing v2 installation, reuse the same prefix with
`update_existing=True` and the complete approved grant map. This replaces the
allowlist rather than merging it. Remove `seed` after initialization and redeploy;
skip the setup notebook's seed cell thereafter. The update applies the Cosmos
database definition so `ProductPimSearch` is added, while the unchanged
`ProductPim` definition preserves existing products and history. Publish the
updated UDF, then run `PIMv2_01_ProductPimHybridSearch` and require its final
`PASS` message before integrating Rayfin. Do not set `update_existing=True`
against an unrelated installation.

## Current test deployment

Deployed on 2026-10-06 using `jumpstart.install()` to **ADI Osmos Challenge**,
workspace `d0708f52-ffc4-4d3e-9fab-6e85dd3618fc`, with prefix `PIMv2_`:

- [Open ProductPimBackend](https://app.fabric.microsoft.com/groups/d0708f52-ffc4-4d3e-9fab-6e85dd3618fc/userdatafunctions/758636a3-bb2b-4071-bdc8-ba739e611efd).
- [Open setup notebook](https://app.fabric.microsoft.com/groups/d0708f52-ffc4-4d3e-9fab-6e85dd3618fc/synapsenotebooks/21e32944-d29d-4447-ac12-40e7d81f016c).
- Cosmos database item: `62bd3d60-1336-40f0-a051-6a63929974d4`.

The API readback verified the four function declarations, dependency pins,
private wheel bytes, approved caller grants and injected database references.
The user subsequently ran the setup notebook successfully on 2026-10-06.
Seed/reseed, product read, update/replay, changed-operation and stale-version
rejection, and paginated audit history passed. Bike version advanced from 1 to 2
once, with the verified caller and invocation recorded. This is user-provided
live evidence, not an agent-run test. Only the approved signed-in user
received `read`, `write`, and temporary `seed` backend grants. Existing v1 items
were not updated. See the changelog for the exact deployment record.

Still **not run**: denied second caller, granted second caller with distinct audit
identity, simultaneous same-version writes, and lost-response fault injection.
Partition/retention review and removal of the temporary `seed` grant are pending.
AI generation, proposal approval/rejection and latency have not been tested or
implemented. The backend is not yet ready for the planned AI UI.

## Rebuild the UDF payload

`backend.py` and `function_app.py` are the editable source. The supported private
wheel contains the backend module; the deployed adapter imports it. The build
uses only the Python standard library, creates deterministic wheel RECORD hashes,
and generates public parameter metadata separately from injected context/connection
bindings. Do not manually edit the generated UDF item.

From this directory:

```powershell
python build_artifacts.py
python build_artifacts.py --check
```

The runtime pins are `fabric-user-data-functions==1.0` and
`azure-cosmos==4.16.4`, matching the existing v1 deployment. Local packaging tests
load the actual generated backend wheel but stub Fabric/Cosmos, so they do not
certify those SDK versions or private-library publication in Fabric.

## Validation and release gates

Local test command from `src/fabric_jumpstart`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cosmos_product_pim.py -q
```

Tests use an in-memory transactional store and a stubbed Fabric runtime. They
validate request construction, rollback expectations, permissions and retries,
not Cosmos service atomicity or Fabric's real authentication boundary.

- Implemented locally: mutation core, context adapter, deny-by-default grants,
  reads/history, deterministic seed, soft-delete/restore, concurrency and receipts.
- Packaged locally: UDF adapter/private wheel, dependency pins, injected identity
  bindings and generated public function metadata; setup/acceptance notebook.
- Validated locally: registry/schema, explicit grants, generated artifact freshness,
  packaged adapter imports, and two full notebook runs against a transactional stub.
- Deployed: isolated Cosmos database, backend UDF/private wheel and setup notebook.
  API readback verifies the UDF payload and injected settings.
- Live single-user acceptance: seed/reseed, reads, update/replay, conflict checks
  and paginated audit history, including verified caller identity. This exercises
  the published private wheel and generic Cosmos connection.
- Pending: live review of `/productId` and TTL, verified context for two callers,
  least-privilege access, actual concurrent/lost-response outcomes and seed removal.
- Pending: AI capability spike, proposal lifecycle and grounded-output validation.
- Registered locally: unique numeric ID 33 and local bundled source. Pending:
  owner group, public release/pinned source if moved to a remote registry entry,
  and complete live functional acceptance. Item creation through `jumpstart.install()`
  and deployed UDF payload readback succeeded in the test workspace.
- Rayfin begins only after backend acceptance; Power BI stays deferred.

No commit, tag, push, or public release is performed by the packaging step.
Live deployment outcomes are recorded separately in the changelog.

## Official references

- [Fabric UDF programming model and verified caller context](https://learn.microsoft.com/en-us/fabric/data-engineering/user-data-functions/python-programming-model)
- [Cosmos transactional batches](https://learn.microsoft.com/en-us/azure/cosmos-db/transactional-batch)
- [Python Cosmos SDK batch options](https://learn.microsoft.com/en-us/python/api/overview/azure/cosmos-readme)
- [Fabric AI Functions](https://learn.microsoft.com/en-us/fabric/data-science/ai-functions/overview)
- [Fabric Apps and Rayfin](https://learn.microsoft.com/en-us/fabric/apps/overview)