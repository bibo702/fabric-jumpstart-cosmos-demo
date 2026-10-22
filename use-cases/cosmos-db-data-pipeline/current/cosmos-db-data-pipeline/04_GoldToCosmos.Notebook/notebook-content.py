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

# # Gold to Cosmos DB
#
# Produces API-ready product insight and category KPI documents. In connected
# mode it creates and upserts two Cosmos DB containers. In smoke-test mode it
# persists the exact documents as Delta tables for inspection without external
# writes. Both paths finish with count assertions and a `gold.pipeline_run_log`
# record.

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

import time
from datetime import datetime, timezone

from pyspark.sql import functions as F

products = spark.table("gold.dim_products")
categories = spark.table("gold.dim_categories")
reviews = spark.table("gold.fact_reviews")

review_metrics = reviews.groupBy("product_id").agg(
    F.avg("stars").alias("avg_rating"),
    F.count("review_id").alias("review_count"),
    F.sum(F.when(F.col("sentiment_bucket") == "positive", 1).otherwise(0)).alias("positive_reviews")
)
product_insights = (
    products.join(review_metrics, "product_id", "left")
    .select(
        F.col("product_id").alias("id"),
        F.lit("product-insight").alias("docType"),
        F.col("category_name").alias("categoryName"),
        F.col("product_name").alias("name"),
        F.col("current_price").alias("currentPrice"),
        "inventory",
        F.coalesce("avg_rating", F.lit(0.0)).alias("avgRating"),
        F.coalesce("review_count", F.lit(0)).alias("reviewCount"),
        F.coalesce("positive_reviews", F.lit(0)).alias("positiveReviews"),
        F.lit(run_id).alias("pipelineRunId")
    )
)

category_reviews = reviews.groupBy("category_name").agg(F.avg("stars").alias("avg_rating"), F.count("review_id").alias("review_count"))
category_dashboard = (
    categories.join(category_reviews, "category_name", "left")
    .select(
        F.concat(F.lit("category-"), F.sha2("category_name", 256)).alias("id"),
        F.lit("category-kpi").alias("docType"),
        F.col("category_name").alias("categoryName"),
        F.col("product_count").alias("productCount"),
        F.col("avg_price").alias("averagePrice"),
        F.col("total_inventory").alias("totalInventory"),
        F.coalesce("avg_rating", F.lit(0.0)).alias("avgRating"),
        F.coalesce("review_count", F.lit(0)).alias("reviewCount"),
        F.lit(run_id).alias("pipelineRunId")
    )
)

product_count = product_insights.count()
category_count = category_dashboard.count()
if product_count == 0 or category_count == 0:
    raise ValueError("Reverse ETL validation produced no documents")

status = "smoke-test"
if cosmos_endpoint.strip():
    from azure.core.credentials import AccessToken, TokenCredential
    from azure.cosmos import CosmosClient, PartitionKey
    import notebookutils

    class FabricTokenCredential(TokenCredential):
        def get_token(self, *scopes, **kwargs):
            token = notebookutils.credentials.getToken("https://cosmos.azure.com/.default")
            return AccessToken(token, int(time.time()) + 3000)

    database = CosmosClient(cosmos_endpoint, credential=FabricTokenCredential()).get_database_client(cosmos_database)
    product_container = database.create_container_if_not_exists(id="product-insights", partition_key=PartitionKey(path="/categoryName"))
    category_container = database.create_container_if_not_exists(id="category-dashboard", partition_key=PartitionKey(path="/categoryName"))
    for row in product_insights.collect():
        product_container.upsert_item(row.asDict(recursive=True))
    for row in category_dashboard.collect():
        category_container.upsert_item(row.asDict(recursive=True))
    status = "cosmos-upserted"
else:
    product_insights.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("gold.product_insights_export")
    category_dashboard.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("gold.category_dashboard_export")

completed_at = datetime.now(timezone.utc).isoformat()
run_log = spark.createDataFrame([(run_id, pipeline_name, status, product_count, category_count, completed_at)], ["run_id", "pipeline_name", "status", "product_count", "category_count", "completed_at"])
run_log.write.mode("append").saveAsTable("gold.pipeline_run_log")

print({"status": status, "product_insights": product_count, "category_dashboard": category_count, "run_id": run_id})

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }