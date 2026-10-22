# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "a1111111-1111-4111-8111-111111111111",
# META       "default_lakehouse_name": "CosmosPipelineLakehouse",
# META       "default_lakehouse_workspace_id": "00000000-0000-0000-0000-000000000000",
# META       "known_lakehouses": [{"id": "a1111111-1111-4111-8111-111111111111"}]
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Cosmos DB Medallion Pipeline
#
# This Jumpstart implements the Azure Cosmos DB sample's complete flow:
# `Cosmos DB -> Bronze -> Silver -> Gold -> Cosmos DB`.
#
# ## Before the first connected run
#
# 1. Create a **Cosmos DB database** in this Fabric workspace.
# 2. On its home page, load **Sample data** to create `SampleData`.
# 3. Copy the database URI from **Settings > Connection**.
# 4. Open `CosmosDB_ETL_Pipeline`, set `cosmos_endpoint` and
#    `cosmos_database`, then select **Run**.
#
# Leave `cosmos_endpoint` empty for the first smoke test. The notebook creates
# deterministic product and review documents locally, allowing the entire
# medallion path to be tested without changing Cosmos DB. A connected run reads
# `SampleData` and the final notebook upserts `product-insights` and
# `category-dashboard` containers.
#
# Source: https://github.com/AzureCosmosDB/cosmos-fabric-samples/tree/main/data-pipelines

# CELL ********************

cosmos_endpoint = ""
cosmos_database = "ProductCatalog"
run_id = "interactive"
pipeline_name = "CosmosDB_ETL_Pipeline"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "tags": ["parameters"]
# META }

# CELL ********************

import json
import time

from pyspark.sql import functions as F

spark.sql("CREATE SCHEMA IF NOT EXISTS bronze")
spark.sql("CREATE SCHEMA IF NOT EXISTS silver")
spark.sql("CREATE SCHEMA IF NOT EXISTS gold")

sample_documents = [
    {"id": "p-100", "docType": "product", "productId": "p-100", "categoryName": "Bikes", "name": "Trail Bike", "currentPrice": 1299.0, "inventory": 18, "priceHistory": [{"date": "2026-07-01", "price": 1399.0}, {"date": "2026-08-01", "price": 1299.0}]},
    {"id": "p-200", "docType": "product", "productId": "p-200", "categoryName": "Accessories", "name": "Touring Helmet", "currentPrice": 89.0, "inventory": 42, "priceHistory": [{"date": "2026-07-01", "price": 95.0}, {"date": "2026-08-01", "price": 89.0}]},
    {"id": "r-101", "docType": "review", "productId": "p-100", "categoryName": "Bikes", "stars": 5, "reviewText": "Fast and comfortable"},
    {"id": "r-102", "docType": "review", "productId": "p-100", "categoryName": "Bikes", "stars": 4, "reviewText": "Excellent trail handling"},
    {"id": "r-201", "docType": "review", "productId": "p-200", "categoryName": "Accessories", "stars": 5, "reviewText": "Lightweight and secure"}
]

source_mode = "generated"
documents = sample_documents

if cosmos_endpoint.strip():
    from azure.core.credentials import AccessToken, TokenCredential
    from azure.cosmos import CosmosClient
    import notebookutils

    class FabricTokenCredential(TokenCredential):
        def get_token(self, *scopes, **kwargs):
            token = notebookutils.credentials.getToken("https://cosmos.azure.com/.default")
            return AccessToken(token, int(time.time()) + 3000)

    client = CosmosClient(cosmos_endpoint, credential=FabricTokenCredential())
    container = client.get_database_client(cosmos_database).get_container_client("SampleData")
    documents = list(container.query_items("SELECT * FROM c", enable_cross_partition_query=True))
    source_mode = "cosmos"

if not documents:
    raise ValueError("No source documents were found in Cosmos DB SampleData")

bronze_df = spark.read.json(spark.sparkContext.parallelize([json.dumps(item) for item in documents]))
bronze_df.withColumn("_ingested_at", F.current_timestamp()).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("bronze.SampleData")

config_df = spark.createDataFrame([(cosmos_endpoint, cosmos_database, source_mode, run_id, pipeline_name)], ["cosmos_endpoint", "cosmos_database", "source_mode", "run_id", "pipeline_name"])
config_df.write.mode("overwrite").saveAsTable("bronze.pipeline_config")

print(f"Bronze ready: {bronze_df.count()} documents ({source_mode} mode)")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }