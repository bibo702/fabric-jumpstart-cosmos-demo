# Fabric backend

## Files

- `backend.py`: product storage, authorization, auditing and search logic.
- `function_app.py`: authored Fabric UDF adapter.
- `build_artifacts.py`: deterministic UDF/private-wheel builder.
- `ProductPimBackend.UserDataFunction/`: generated deployment payload.
- `_provisioning/cosmos-definition.json`: authoritative and derived-search
  container definitions.
- `00_ProductPimSetup.Notebook/`: seed, mutation, retry and audit checks.
- `01_ProductPimHybridSearch.Notebook/`: synthetic search data and comparison.
- `02_ProductPimReindex.Notebook/`: incremental embedding/index refresh.

## Configure and publish

Use a separate, approved capacity-backed Fabric workspace. No script in this
repository provisions resources or modifies a deployment automatically.

1. Create a Cosmos DB in Fabric database. Configure `ProductPim` and
   `ProductPimSearch` using the partition, TTL, vector and full-text policies in
   [_provisioning/cosmos-definition.json](_provisioning/cosmos-definition.json).
   Both containers use `/productId`; the search container is derived data.
2. In [function_app.py](function_app.py), set `COSMOS_URI` to the database's
   artifact URI and `DATABASE_NAME` to its database name. Replace the empty
   `PRINCIPAL_GRANTS` with explicitly approved `tenant-guid:object-guid` keys
   and roles. The backend intentionally rejects callers when grants are empty.
   Use `read`/`write`, and grant `seed` only for initialization.
3. Build the configured UDF payload:

   ```powershell
   python backend\build_artifacts.py
   python backend\build_artifacts.py --check
   ```

   Run these commands from the repository root. Configure before building;
   generated files are not the authored source.
4. Create/update a Fabric User Data Functions item named `ProductPimBackend`
   using the generated payload, its private backend wheel and the dependency/
   binding metadata. Complete its Cosmos connection configuration and publish it.
   This repository does not replace Fabric's item publication workflow.
5. Create/import the three Fabric notebooks from their source definitions.
   If you use different item names, set each notebook's `udf_item_name` and the
   search notebook's reindex-notebook parameter to the deployed names.
   Set the setup notebook's `database_name` to your actual database name.
6. Run `00_ProductPimSetup`. Then run `01_ProductPimHybridSearch` with
   `seed_demo=True` for the deterministic 1,200-product dataset and all three
   preset comparisons. Review the notebook's results; do not assume acceptance.
7. Remove temporary `seed` grants, rebuild and republish the UDF. Use
   `seed_demo=False` for later search checks.
8. Validate `02_ProductPimReindex` manually, then optionally schedule it in Fabric.
   Its execution identity needs both `read` and `write` grants. Avoid overlapping
   runs and monitor failures. Installation does not enable a schedule.

Never commit tokens or credentials. Do not reuse historical workspace IDs.
Only configure approved identities, including the app owner's downstream identity.

## Boundaries

Products are authoritative; the search index can lag. Writes are atomic per
product and use version checks plus operation IDs for retry safety. Stale search
hits are suppressed, and missing freshness checks are not reported as current.
The 1,200-vector dataset clears the documented minimum for DiskANN, but does not
prove index execution or performance. Check live diagnostics and relevance.

AI-description proposals, conversational shopping and reporting are not exposed
by this demo. The retained backend source includes internal experimental helpers;
they are not published UDF operations.
