# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Cosmos Product PIM: Native Hybrid Search Acceptance
#
# This notebook builds and verifies semantic product retrieval using only native
# Microsoft Fabric capabilities:
#
# - Fabric AI Functions `ai.embed` creates 1,536-dimensional embeddings.
# - Cosmos DB in Fabric stores search documents beside the authoritative catalog.
# - A native DiskANN vector index and full-text BM25 index rank results together.
# - Cosmos DB `RRF` fuses both rankings in one parameterized NoSQL query.
#
# The installer creates the `ProductPimSearch` container with its immutable vector
# policy. If this scenario was deployed before hybrid search was added, update the
# Cosmos item so Fabric creates that container, then republish the updated UDF.
# Do not add an Azure AI Search service or a separate Azure Cosmos DB account.

# CELL ********************

udf_item_name = "ProductPimBackend"
query_text = "lightweight shelter for two campers"
expected_dimensions = 1536

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "tags": ["parameters"]
# META }

# CELL ********************

import json

import notebookutils
import synapse.ml.spark.aifunc as aifunc
from IPython.display import Markdown, display

pim = notebookutils.udf.getFunctions(udf_item_name)
display(pim.functionDetails)


def result_object(value):
    result = json.loads(value) if isinstance(value, str) else value
    assert isinstance(result, dict), "Expected a UDF JSON object"
    assert result.get("status") not in {"failed", "rejected"}, result
    return result


def embedding_list(value):
    vector = value.toArray().tolist() if hasattr(value, "toArray") else list(value)
    assert len(vector) == expected_dimensions, (
        f"Fabric ai.embed returned {len(vector)} dimensions; "
        f"ProductPimSearch requires {expected_dimensions}."
    )
    return [float(item) for item in vector]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Read the authoritative product catalog
#
# This uses the authorized PIM UDF rather than database credentials. Run the setup
# notebook first if the catalog is empty.

# CELL ********************

products = []
after_product_id = ""
for page_number in range(1000):
    page = result_object(
        pim.list_products(pageSize=100, afterProductId=after_product_id)
    )
    products.extend(page["items"])
    after_product_id = page["afterProductId"]
    if not after_product_id:
        break
else:
    raise RuntimeError("Catalog exceeded the notebook's 1000-page safety limit")

assert products, "No products found. Run 00_ProductPimSetup first."
display(Markdown(f"Loaded **{len(products)}** authoritative products."))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Generate and persist Fabric-native embeddings
#
# Search text is derived from the current product fields. The UDF reloads each
# product, verifies its version, rebuilds the same text server-side, and writes
# only the derived search document. Rerunning this cell refreshes stale entries.

# CELL ********************

embedding_input = [
    (
        product["productId"],
        product["version"],
        "\n".join(
            [
                product["name"],
                product["categoryName"],
                product["description"],
                " ".join(product.get("marketing", {}).get("seoKeywords", [])),
            ]
        ).strip(),
    )
    for product in products
]
source = spark.createDataFrame(
    embedding_input, ["productId", "expectedVersion", "searchText"]
)
embedded = source.ai.embed(
    input_col="searchText", output_col="embedding", error_col="embeddingError"
)
rows = embedded.collect()
assert all(row["embeddingError"] is None for row in rows), rows

indexed = []
for row in rows:
    indexed.append(
        result_object(
            pim.index_product_search(
                payload={
                    "productId": row["productId"],
                    "expectedVersion": row["expectedVersion"],
                    "embedding": embedding_list(row["embedding"]),
                }
            )
        )
    )

assert len(indexed) == len(products), indexed
assert all(item["status"] == "indexed" for item in indexed), indexed
display(indexed)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Execute DiskANN + BM25 + RRF
#
# Fabric embeds the free-text query with the same model. The UDF validates the
# vector and executes a parameterized native Cosmos query:
# `RRF(VectorDistance(...), FullTextScore(...))`.

# CELL ********************

query_frame = spark.createDataFrame([(query_text,)], ["queryText"])
query_embedded = query_frame.ai.embed(
    input_col="queryText", output_col="embedding", error_col="embeddingError"
).first()
assert query_embedded["embeddingError"] is None, query_embedded["embeddingError"]

search = result_object(
    pim.search_products(
        queryText=query_text,
        queryVector=embedding_list(query_embedded["embedding"]),
        pageSize=10,
        status="active",
    )
)
assert search["ranking"] == "RRF(DiskANN cosine, BM25)", search
assert search["items"], search
assert all(item["status"] == "active" for item in search["items"]), search
display(search)
print("PASS: Fabric ai.embed -> Cosmos DiskANN + BM25 -> RRF hybrid ranking")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
