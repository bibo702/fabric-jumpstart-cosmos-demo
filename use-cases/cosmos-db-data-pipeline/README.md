# Cosmos DB medallion data pipeline

- [Current tutorial](current/): Cosmos DB to Bronze, Silver and Gold Lakehouse
  tables, then enriched products and category summaries back to Cosmos DB.
- Entry point: `00_CosmosDBPipelineSetup.Notebook`.
- Logical ID: `cosmos-db-data-pipeline`.

The initial smoke-test mode uses deterministic generated documents. A connected
run requires the Cosmos endpoint/database configuration described in the setup
notebook. The export does not claim a live connected run.

See [all use cases](../README.md) for installation and maintenance guidance.
