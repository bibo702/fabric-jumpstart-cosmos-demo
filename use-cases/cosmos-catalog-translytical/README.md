# Catalog analytics and price write-back

| Version | Use case | Source |
| --- | --- | --- |
| [v1.0](v1.0/) | Three-product catalog, SQL mirror and single-product audited price changes | Stable historical commit `1a496312061d7c7f790e5f88c463163c46a08111` |
| [v1.1](v1.1/) | 120 products, six categories, bulk percentage changes and price-audit history | Stable historical commit `95c6cf12adb2aaf9064ec103d3ad96fad393e7ea` |

Both versions use logical ID `cosmos-catalog-translytical` and start with
`00_CosmosCatalogSetup.Notebook`, followed by `01_CosmosCatalogWriteback.Notebook`.
Use separate prefixes/workspaces to compare them without overwriting a deployment.
These folders preserve historical source; no new live validation is claimed.

See [all use cases](../README.md) for installation and maintenance guidance.
