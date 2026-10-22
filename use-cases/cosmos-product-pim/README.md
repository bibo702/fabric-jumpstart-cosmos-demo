# Product PIM, search and Rayfin

| Version | Use case | Readiness |
| --- | --- | --- |
| [v2.0 checkpoint](v2.0-checkpoint/) | Product-partitioned catalog, verified caller, atomic audit and retry receipts | Historical pre-Rayfin WIP; source and generated artifacts differ |
| [v0.3.0](v0.3.0/) | Native vector/BM25/RRF hybrid search with Fabric embeddings | Tagged snapshot; app search integration still gated at this milestone |
| [v0.3.1](v0.3.1/) | Stored semantic-query presets and authenticated Rayfin search | Tagged snapshot |
| [v0.3.2](v0.3.2/) | Free-text product-name search plus semantic presets | Tagged snapshot |
| [v0.4.0 unreleased](v0.4.0-unreleased/) | Catalog browsing/creation, deterministic 1,200-product dataset and incremental reindex worker | Local implementation; live acceptance pending |

Each folder includes a separate `cosmos-product-pim` Fabric source tree and
registration. The 0.3.x and 0.4.0 folders also include the matching `app` source.
The backend wheel's 0.3.x numbering is distinct from the earlier "v2.0" project
milestone and from the Python library's version.

Logical ID: `cosmos-product-pim`. Entry point: `00_ProductPimSetup.Notebook`.
The Python installer does not deploy the Rayfin AppBackend. Follow that version's
app instructions separately, using explicit approved configuration.

The v2.1 AI-proposal experiment is deferred; `probe_ai_connection.py` in the
checkpoint is an experiment, not an accepted AI implementation. No conversational
shopping or Power BI implementation is implied.

See [all use cases](../README.md) for installation and maintenance guidance.
