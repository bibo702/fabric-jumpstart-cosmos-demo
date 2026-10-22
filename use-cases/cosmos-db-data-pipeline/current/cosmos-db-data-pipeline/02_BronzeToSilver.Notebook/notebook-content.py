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

# # Bronze to Silver
#
# Splits the mixed `bronze.SampleData` documents into typed product, review,
# and price-history tables. Invalid records are excluded and counted.

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

bronze = spark.table("bronze.SampleData")
doc_type = F.lower(F.coalesce(F.col("docType"), F.lit("")))

products = (
    bronze.filter(doc_type.isin("product", "products"))
    .select(
        F.coalesce(F.col("productId"), F.col("id")).alias("product_id"),
        F.col("categoryName").alias("category_name"),
        F.col("name").alias("product_name"),
        F.col("currentPrice").cast("double").alias("current_price"),
        F.coalesce(F.col("inventory").cast("long"), F.lit(0)).alias("inventory"),
        F.col("priceHistory").alias("price_history")
    )
    .filter(F.col("product_id").isNotNull() & F.col("category_name").isNotNull())
)

reviews = (
    bronze.filter(doc_type.isin("review", "reviews"))
    .select(
        F.col("id").alias("review_id"),
        F.col("productId").alias("product_id"),
        F.col("categoryName").alias("category_name"),
        F.col("stars").cast("int").alias("stars"),
        F.col("reviewText").alias("review_text")
    )
    .filter(F.col("product_id").isNotNull() & F.col("stars").between(1, 5))
    .withColumn("sentiment_bucket", F.when(F.col("stars") >= 4, "positive").when(F.col("stars") <= 2, "negative").otherwise("neutral"))
)

price_history = (
    products.select("product_id", "category_name", F.explode_outer("price_history").alias("change"))
    .select("product_id", "category_name", F.to_date("change.date").alias("price_date"), F.col("change.price").cast("double").alias("price"))
    .filter(F.col("price_date").isNotNull() & F.col("price").isNotNull())
)

products.drop("price_history").write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver.products")
reviews.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver.reviews")
price_history.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver.price_history")

print({"products": products.count(), "reviews": reviews.count(), "price_history": price_history.count()})

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }