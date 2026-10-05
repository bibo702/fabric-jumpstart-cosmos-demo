# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Cosmos Catalog Live Analytics and Write-back
#
# This v1 Jumpstart implements:
#
# `Cosmos DB in Fabric -> SQL analytics endpoint -> User Data Function -> Cosmos DB`
#
# Cosmos DB is the operational system of record. Its built-in mirroring is the
# only analytics ingestion path; this notebook never copies catalog data into a
# Lakehouse.
#
# ## Run the demo
#
# The Jumpstart installation creates the Cosmos DB database and `SampleData`
# container, then configures this notebook and `PriceWriteback` with the generated
# endpoint. No account keys, connection strings, or manual endpoint setup are needed.
#
# 1. Run all cells to seed the sample products.
# 2. In the Cosmos item, verify that the `SampleData` container is visible through
#    the generated SQL analytics endpoint.
# 3. Open `PriceWriteback` and publish it.
# 4. In `PriceWriteback` Develop mode, test `update_prices` with the current
#    product version. A successful update returns `status: applied` and increments
#    the version. Validation failures return `status: rejected`; stale versions
#    return `status: conflict` while the Fabric invocation itself still succeeds.
# 5. In the SQL analytics endpoint, verify both the updated product and its
#    immutable `priceChange` audit document.
#
# The connection uses your Fabric identity. Do not paste account keys or
# connection strings into this notebook.
#
# ## Acceptance test
#
# Use this request after the initial seed:
#
# ```json
# [{"productId":"helmet-200","categoryName":"Accessories","newPrice":95,
#   "reason":"Jumpstart acceptance test","expectedVersion":1}]
# ```
#
# Set `requestedBy` to your email address. The expected result has
# `status: applied` and `version: 2`. Run the same request again to confirm it
# returns `status: conflict` without changing the product.
#
# Query the generated SQL analytics endpoint after mirroring catches up:
#
# ```sql
# SELECT id, currentPrice, version, updatedBy, updatedAt
# FROM dbo.SampleData
# WHERE docType = 'product';
#
# SELECT id, productId, oldPrice, newPrice, reason, requestedBy, productVersion
# FROM dbo.SampleData
# WHERE docType = 'priceChange';
# ```

# CELL ********************

%pip install azure-cosmos==4.16.4

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

cosmos_endpoint = "{my-cosmos-artifact-uri}"
database_name = "{my-cosmos-database-name}"
container_name = "SampleData"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "tags": ["parameters"]
# META }

# CELL ********************

import time

from azure.core.credentials import AccessToken, TokenCredential
from azure.cosmos import CosmosClient
import notebookutils

class FabricTokenCredential(TokenCredential):
    def get_token(self, *scopes, **kwargs):
        token = notebookutils.credentials.getToken("https://cosmos.azure.com/.default")
        return AccessToken(token, int(time.time()) + 3000)


client = CosmosClient(cosmos_endpoint, credential=FabricTokenCredential())
database = client.get_database_client(database_name)
container = database.get_container_client(container_name)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

sample_products = [
    {
        "id": "bike-100",
        "docType": "product",
        "productId": "bike-100",
        "categoryName": "Bikes",
        "sku": "BK-TRAIL-100",
        "name": "Trail Bike Pro",
        "brand": "Northwind Cycles",
        "currentPrice": 1299.99,
        "currency": "USD",
        "inventory": 18,
        "isActive": True,
        "version": 1,
        "updatedAt": "2026-09-09T00:00:00Z",
        "updatedBy": "jumpstart-seed",
        "attributes": [
            {"key": "frameSize", "type": "string", "value": "Large"},
            {"key": "material", "type": "string", "value": "Carbon Fiber"},
            {"key": "wheelSize", "type": "number", "value": 29},
        ],
    },
    {
        "id": "helmet-200",
        "docType": "product",
        "productId": "helmet-200",
        "categoryName": "Accessories",
        "sku": "AC-HELMET-200",
        "name": "Touring Helmet",
        "brand": "Alpine Works",
        "currentPrice": 89.0,
        "currency": "USD",
        "inventory": 42,
        "isActive": True,
        "version": 1,
        "updatedAt": "2026-09-09T00:00:00Z",
        "updatedBy": "jumpstart-seed",
        "attributes": [
            {"key": "size", "type": "string", "value": "Medium"},
            {"key": "color", "type": "string", "value": "Signal Red"},
            {"key": "weightGrams", "type": "number", "value": 280},
        ],
    },
    {
        "id": "tent-300",
        "docType": "product",
        "productId": "tent-300",
        "categoryName": "Camping",
        "sku": "CP-TENT-300",
        "name": "Three Person Trek Tent",
        "brand": "Fourth Coffee Outdoor",
        "currentPrice": 249.5,
        "currency": "USD",
        "inventory": 9,
        "isActive": True,
        "version": 1,
        "updatedAt": "2026-09-09T00:00:00Z",
        "updatedBy": "jumpstart-seed",
        "attributes": [
            {"key": "capacity", "type": "number", "value": 3},
            {"key": "seasonRating", "type": "string", "value": "3-season"},
            {"key": "packedWeightKg", "type": "number", "value": 2.4},
        ],
    },
]

for product in sample_products:
    try:
        container.create_item(product)
        print(f"Created {product['id']}")
    except Exception as error:
        if getattr(error, "status_code", None) == 409:
            print(f"Kept existing {product['id']}")
        else:
            raise

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

products = list(
    container.query_items(
        "SELECT c.id, c.productId, c.categoryName, c.name, c.currentPrice, c.version "
        "FROM c WHERE c.docType = 'product'",
        enable_cross_partition_query=True,
    )
)
if len(products) < len(sample_products):
    raise RuntimeError("Catalog verification failed: seeded products are missing.")

display(products)
print("Catalog ready. Continue in the generated SQL analytics endpoint.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }