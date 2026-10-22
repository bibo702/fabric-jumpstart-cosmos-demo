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

# # Silver to Gold
#
# Builds a compact star schema for product, category, review, and price-change
# analytics. Every write is idempotent so test runs can be repeated safely.

# CELL ********************

run_id = "interactive"
pipeline_name = "CosmosDB_ETL_Pipeline"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "tags": ["parameters"]
# META }

# CELL ********************

from pyspark.sql import functions as F

products = spark.table("silver.products")
reviews = spark.table("silver.reviews")
price_history = spark.table("silver.price_history")

dim_products = products.select("product_id", "category_name", "product_name", "current_price", "inventory")
dim_categories = (
    products.groupBy("category_name")
    .agg(
        F.countDistinct("product_id").alias("product_count"),
        F.avg("current_price").alias("avg_price"),
        F.min("current_price").alias("min_price"),
        F.max("current_price").alias("max_price"),
        F.sum("inventory").alias("total_inventory")
    )
)
dim_date = price_history.select(F.col("price_date").alias("date")).distinct().withColumn("year", F.year("date")).withColumn("month", F.month("date"))
fact_reviews = reviews.select("review_id", "product_id", "category_name", "stars", "sentiment_bucket")
fact_price_changes = price_history.select("product_id", "category_name", "price_date", "price")

tables = {
    "gold.dim_products": dim_products,
    "gold.dim_categories": dim_categories,
    "gold.dim_date": dim_date,
    "gold.fact_reviews": fact_reviews,
    "gold.fact_price_changes": fact_price_changes
}
for table_name, dataframe in tables.items():
    dataframe.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table_name)

counts = {name: dataframe.count() for name, dataframe in tables.items()}
if counts["gold.dim_products"] == 0 or counts["gold.dim_categories"] == 0:
    raise ValueError(f"Gold validation failed: {counts}")
print(counts)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }