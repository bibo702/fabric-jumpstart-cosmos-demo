# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Incremental Product PIM search indexing
#
# Configure a Fabric notebook schedule for this item after the first successful
# interactive run. This is a polling worker, not a change-feed processor. Each run
# scans authoritative product versions and embeds only missing or stale entries.
# The invoking identity requires read/write grants but never seed grants.
# Spark startup plus the chosen schedule determines freshness; it is not instant.
# Failed runs remain failed and can be retried safely. No product or audit is
# modified. Concurrent edits are left pending for the next run, not overwritten.

# CELL ********************

udf_item_name = "ProductPimBackend"
page_size = 50
max_pages = 1000
expected_dimensions = 1536

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "tags": ["parameters"]
# META }

# CELL ********************

import json
import math

import notebookutils
import synapse.ml.spark.aifunc as aifunc

pim = notebookutils.udf.getFunctions(udf_item_name)
if type(page_size) is not int or not 1 <= page_size <= 100:
    raise ValueError("page_size must be between 1 and 100")
if type(max_pages) is not int or not 1 <= max_pages <= 10000:
    raise ValueError("max_pages must be between 1 and 10000")


def result_object(value):
    result = json.loads(value) if isinstance(value, str) else value
    if not isinstance(result, dict) or result.get("status") in {"failed", "rejected"}:
        raise RuntimeError(f"PIM indexing operation failed: {result}")
    return result


def embedding_list(value):
    vector = value.toArray().tolist() if hasattr(value, "toArray") else list(value)
    if len(vector) != expected_dimensions or not all(math.isfinite(float(item)) for item in vector):
        raise ValueError("Fabric embedding dimensions/values do not match the search policy")
    return [float(item) for item in vector]


after_product_id = ""
seen_cursors = set()
scanned_count = 0
indexed_count = 0
conflicted_ids = []
for page_number in range(max_pages):
    page = result_object(pim.list_pending_search(
        pageSize=page_size, afterProductId=after_product_id,
    ))
    scanned_count += page["scannedCount"]
    pending = page["items"]
    if pending:
        embedding_input = [
            (
                product["productId"], product["version"],
                "\n".join([
                    product["name"], product["categoryName"], product["description"],
                    " ".join(product.get("marketing", {}).get("seoKeywords", [])),
                ]).strip(),
            )
            for product in pending
        ]
        source = spark.createDataFrame(
            embedding_input, ["productId", "expectedVersion", "searchText"],
        )
        rows = source.ai.embed(
            input_col="searchText", output_col="embedding", error_col="embeddingError",
        ).collect()
        if len(rows) != len(pending) or any(row["embeddingError"] is not None for row in rows):
            raise RuntimeError("Fabric embedding failed; rerun the worker after resolving the error")
        for row in rows:
            raw = pim.index_product_search(payload={
                "productId": row["productId"], "expectedVersion": row["expectedVersion"],
                "embedding": embedding_list(row["embedding"]),
            })
            outcome = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(outcome, dict) and outcome.get("status") == "rejected" and outcome.get("code") == "version_conflict":
                conflicted_ids.append(row["productId"])
                print(f"Concurrent edit: {row['productId']} remains pending for the next run.")
                continue
            result = result_object(outcome)
            if result.get("status") != "indexed":
                raise RuntimeError(f"Unexpected indexing outcome: {result}")
            indexed_count += 1
    after_product_id = page["afterProductId"]
    if not after_product_id:
        break
    if after_product_id in seen_cursors:
        raise RuntimeError("Catalog pagination repeated a cursor")
    seen_cursors.add(after_product_id)
else:
    raise RuntimeError("Catalog scan exceeded max_pages; increase the bound explicitly")

summary = {
    "scannedCount": scanned_count,
    "indexedCount": indexed_count,
    "concurrentEditCount": len(conflicted_ids),
    "concurrentProductIds": conflicted_ids,
}
print(json.dumps(summary))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
