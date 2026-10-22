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
# Create the `ProductPimSearch` container with the vector and full-text policies
# from `_provisioning/cosmos-definition.json`, then publish the backend UDF
# before running this notebook. See the backend README for setup.
# Do not add an Azure AI Search service or a separate Azure Cosmos DB account.

# CELL ********************

udf_item_name = "ProductPimBackend"
reindex_notebook_name = "02_ProductPimReindex"
seed_demo = True
demo_catalog_size = 1200
expected_dimensions = 1536
demo_queries = [
    {
        "queryId": "lightweight-shelter",
        "label": "Lightweight shelter",
        "queryText": "lightweight shelter for two campers",
        "expectedCategory": "Camping",
    },
    {
        "queryId": "cycling-safety",
        "label": "Cycling safety",
        "queryText": "protective safety gear for cycling",
        "expectedCategory": "Accessories",
    },
    {
        "queryId": "trail-riding",
        "label": "Trail riding",
        "queryText": "bicycle for riding on outdoor trails",
        "expectedCategory": "Bikes",
    },
]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "tags": ["parameters"]
# META }

# CELL ********************

import json
import math
import time

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
    assert all(math.isfinite(float(item)) for item in vector), "Non-finite embedding"
    return [float(item) for item in vector]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Initialize a meaningful synthetic search catalog
#
# Fabric DiskANN requires at least 1,000 inserted vectors; a smaller dataset uses
# a full scan. Generate 1,200 synthetic products in retryable batches. Existing
# products are never overwritten. Remove seed grants only after this step, then
# set seed_demo=False on subsequent runs. This incurs real Fabric AI and Cosmos
# consumption; no embeddings or database responses are mocked.

# CELL ********************

if type(seed_demo) is not bool:
    raise ValueError("seed_demo must be a boolean")
if demo_catalog_size != 1200:
    raise ValueError("This version defines exactly 1200 deterministic demo products")
if seed_demo:
    for start in range(0, demo_catalog_size, 50):
        seeded = result_object(pim.seed_demo_catalog(start=start, count=50))
        assert len(seeded["items"]) == 50, seeded
        assert all(item["status"] in {"created", "skipped"} for item in seeded["items"]), seeded

notebookutils.notebook.run(
    reindex_notebook_name, 3600, {"udf_item_name": udf_item_name},
)

products = []
after_product_id = ""
seen_cursors = set()
for page_number in range(1000):
    page = result_object(
        pim.list_products(pageSize=100, afterProductId=after_product_id)
    )
    products.extend(page["items"])
    after_product_id = page["afterProductId"]
    if not after_product_id:
        break
    assert after_product_id not in seen_cursors, "Catalog cursor repeated"
    seen_cursors.add(after_product_id)
else:
    raise RuntimeError("Catalog exceeded the notebook's 1000-page safety limit")

assert len(products) >= 1000, "At least 1000 authoritative products are required."
display(Markdown(f"Loaded **{len(products)}** authoritative products."))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Verify current product indexing
#
# The scheduled worker embeds only stale/missing entries using Fabric ai.embed.
# Any concurrently changed product must be caught up before acceptance proceeds.

# CELL ********************

for start in range(0, len(products), 100):
    state = result_object(pim.get_search_index_status(
        productIds=[product["productId"] for product in products[start:start + 100]],
    ))
    assert state["pendingCount"] == 0, "Concurrent edits remain pending; rerun the indexing worker."
    assert all(item["status"] == "current" for item in state["items"]), state

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Publish Fabric-native demo queries
#
# Rayfin cannot invoke notebook `ai.embed` interactively. These transparent,
# named presets let the app exercise the exact Fabric-native hybrid path without
# adding Azure AI Foundry or another embedding service.

# CELL ********************

query_frame = spark.createDataFrame(
    [
        (item["queryId"], item["label"], item["queryText"])
        for item in demo_queries
    ],
    ["queryId", "label", "queryText"],
)
query_embedded = query_frame.ai.embed(
    input_col="queryText", output_col="embedding", error_col="embeddingError"
)
query_rows = query_embedded.collect()
assert all(row["embeddingError"] is None for row in query_rows), query_rows

indexed_queries = [
    result_object(
        pim.index_search_query(
            payload={
                "queryId": row["queryId"],
                "label": row["label"],
                "queryText": row["queryText"],
                "embedding": embedding_list(row["embedding"]),
            }
        )
    )
    for row in query_rows
]
assert all(item["status"] == "indexed" for item in indexed_queries), indexed_queries
display(indexed_queries)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Compare keyword, vector, and hybrid retrieval for every preset
#
# Expected relevance: at least four of the top five results belong to the
# expected category for vector and hybrid retrieval. These are dataset-specific
# acceptance thresholds, not a promise that hybrid always outperforms keyword.
# Request charge covers only the search query, not hydration or the bridge.
# Index/query diagnostics are captured from service headers, never synthesized.
# Inspect them before claiming indexed DiskANN execution; a ranking label alone
# is not proof of index usage. The service may need time to build its index.

# CELL ********************

categories = {product["productId"]: product["categoryName"] for product in products}
measurements = []
for query in demo_queries:
    started_at = time.perf_counter()
    compared = result_object(pim.compare_search_modes(
        queryId=query["queryId"], pageSize=5, status="active",
    ))
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    for mode in ("keyword", "vector", "hybrid"):
        search = compared[mode]
        assert search["queryId"] == query["queryId"], search
        assert len(search["items"]) == 5, search
        assert search["indexingPending"] is False, search
        assert all(item["status"] == "active" for item in search["items"]), search
        relevant = sum(
            categories[item["productId"]] == query["expectedCategory"]
            for item in search["items"]
        )
        if mode in {"vector", "hybrid"}:
            assert relevant >= 4, f"{query['queryId']} {mode} precision@5={relevant / 5}"
        diagnostics = search["diagnostics"]
        assert diagnostics["requestCharge"] is not None, "Service RU diagnostics were not returned."
        measurements.append({
            "queryId": query["queryId"], "mode": mode, "precisionAt5": relevant / 5,
            "diagnostics": diagnostics, "comparisonCallElapsedMs": elapsed_ms,
        })
display(measurements)
print("PASS: all presets executed against Cosmos; vector/hybrid precision@5 >= 0.8.")
print("Index execution and hosted browser authentication still require live evidence review.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
