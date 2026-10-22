# Cosmos and Fabric use cases

Choose a use case, then a version. Each version folder contains actual source
files and Fabric item definitions, following the source-plus-item-tree pattern
in the [SAP manufacturing example](https://github.com/DaSenf1860/jumpstart-sap-manufacturing).
The original library and application paths remain available for development and
installation.

| Use case | Versions | What it demonstrates |
| --- | --- | --- |
| [Hello World](hello-world/) | [Current](hello-world/current/) | Minimal notebook installation smoke test |
| [Cosmos DB data pipeline](cosmos-db-data-pipeline/) | [Current](cosmos-db-data-pipeline/current/) | Bronze/Silver/Gold processing and enriched Cosmos write-back |
| [Catalog analytics and price write-back](cosmos-catalog-translytical/) | [v1.0](cosmos-catalog-translytical/v1.0/), [v1.1](cosmos-catalog-translytical/v1.1/) | SQL mirror, governed price changes and price-audit history |
| [Product PIM and Rayfin](cosmos-product-pim/) | [v2.0 checkpoint](cosmos-product-pim/v2.0-checkpoint/), [v0.3.0](cosmos-product-pim/v0.3.0/), [v0.3.1](cosmos-product-pim/v0.3.1/), [v0.3.2](cosmos-product-pim/v0.3.2/), [v0.4.0 unreleased](cosmos-product-pim/v0.4.0-unreleased/) | Audited product management, native hybrid/name search and app integration |

## Folder pattern

```text
use-cases/
  <use-case>/
    README.md
    <version>/
      README.md
      registration.yml
      <logical-id>/        # Fabric items, provisioning metadata and source
      app/                 # matching Rayfin app, where applicable
```

Versions are isolated copies, not aliases to today's implementation. Historical
copies are byte-for-byte exports from the commits recorded in each version's
README. Current/unreleased copies capture local source at export time and must not be confused
with accepted releases. Version numbers belong to the individual demo/backend,
not the Python library; the historical "v2.0" milestone predates backend wheel
versions 0.3.x.

The v2.1 AI-proposal experiment was deferred, not released. Its probe is preserved
in the pre-Rayfin checkpoint rather than presented as a working AI use case.
Conversational shopping and Power BI reporting remain roadmap items, not folders
with fabricated implementations.

## Using a version

Read its overview and registration first. The snapshots do not introduce a
standalone installer: use the canonical Python library from the corresponding
source revision. Historical registration metadata is preserved, not repointed at
these export folders. The current bundled installer still reads the original
[scenario sources](../src/fabric_jumpstart/fabric_jumpstart/jumpstarts/).
An app is deployed separately from the Fabric database/UDF/notebooks.

No resources are deployed, notebooks run or schedules enabled by generating this
layout. Live validation limitations remain in the version-specific documentation.
Never reuse someone else's recorded workspace IDs, endpoints or grants.

### Historical packaging caveat

The 0.3.0, 0.3.1 and 0.3.2 tagged UDF artifacts contain formatting/line-ending
differences from their builders' strict byte output. Those historical bytes are
preserved, not silently rewritten. Parsed JSON, normalized Python source and
private-wheel bytes match their builders. The unreleased 0.4.0 artifacts pass
the strict builder check. None of these local checks establishes live readiness.

## Maintaining these folders

From the repository root:

```powershell
python tools\scripts\export-use-cases.py --refresh-current
python tools\scripts\export-use-cases.py --check
```

Regeneration requires Git history for the pinned commits; `--check` also works in
a shallow clone. The exporter uses only Python's standard library.
It excludes dependency caches, local settings, environment
files, editor/MCP configuration and deployment state. It never deletes files:
obsolete exports are reported for explicit review. All snapshots have committed
SHA-256 inventories so a fresh clone can verify them without Git history or the
original uncommitted development files. `--refresh-current` rebuilds historical
copies from pinned commits and explicitly updates working-source snapshots;
without it, the exporter preserves and checks the frozen copies.
Edit canonical sources, then regenerate; do not hand-edit version payloads.
The local Git attributes disable line-ending conversion for these copies so their
historical bytes and inventories remain valid on Windows and Linux.
