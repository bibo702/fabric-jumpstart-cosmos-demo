# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Cosmos Catalog Live Analytics and Write-back
#
# This v1.1 Jumpstart implements:
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
# 1. Run all cells to seed 120 deterministic products across six categories and
#    representative historical price changes. Reruns keep existing documents.
# 2. In the Cosmos item, verify that the `SampleData` container is visible through
#    the generated SQL analytics endpoint.
# 3. Open `PriceWriteback` and publish it.
# 4. Open `01_CosmosCatalogWriteback`, run all cells, and use the guided form to
#    filter by category, select up to 25 products, and submit a percentage price
#    change. Successful updates return `status: applied` and increment each
#    product version. Validation failures return `status: rejected`; stale
#    versions return `status: conflict`.
# 5. In the SQL analytics endpoint, verify both the updated product and its
#    immutable `priceChange` audit document.
#
# The connection uses your Fabric identity. Do not paste account keys or
# connection strings into this notebook.
#
# ## Acceptance test
#
# On a fresh deployment, use `01_CosmosCatalogWriteback` to select the Touring
# Helmet and submit a 6.74% adjustment with reason `Jumpstart acceptance test`.
# This is equivalent to the original v1 request:
#
# ```json
# [{"productId":"helmet-200","categoryName":"Accessories","newPrice":95,
#   "reason":"Jumpstart acceptance test","expectedVersion":1}]
# ```
#
# The guided notebook supplies this payload to the function and defaults
# `requestedBy` to your Fabric identity. The expected result has
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

import random
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

seed = random.Random(20261006)
products_per_category = 20
expected_product_count = 120
category_configs = {
    "Bikes": {
        "prefix": "BK",
        "nouns": ["Trail Bike", "Road Bike", "City Bike", "Gravel Bike"],
        "brands": ["Northwind Cycles", "Contoso Racing"],
        "basePrice": 899,
        "attributes": [
            ("frameSize", "string", ["Small", "Medium", "Large"]),
            ("material", "string", ["Aluminum", "Carbon Fiber"]),
            ("wheelSize", "number", [27.5, 29]),
        ],
    },
    "Accessories": {
        "prefix": "AC",
        "nouns": ["Touring Helmet", "Frame Bag", "Floor Pump", "Bike Light"],
        "brands": ["Alpine Works", "Adventure Works"],
        "basePrice": 45,
        "attributes": [
            ("size", "string", ["Small", "Medium", "Large"]),
            ("color", "string", ["Signal Red", "Graphite", "Ocean Blue"]),
            ("weightGrams", "number", [180, 280, 420]),
        ],
    },
    "Camping": {
        "prefix": "CP",
        "nouns": ["Trek Tent", "Camp Stove", "Sleeping Bag", "Trail Lantern"],
        "brands": ["Fourth Coffee Outdoor", "Blue Yonder"],
        "basePrice": 110,
        "attributes": [
            ("capacity", "number", [1, 2, 3, 4]),
            ("seasonRating", "string", ["3-season", "4-season"]),
            ("packedWeightKg", "number", [0.8, 1.6, 2.4]),
        ],
    },
    "Clothing": {
        "prefix": "CL",
        "nouns": ["Trail Jersey", "Rain Shell", "Thermal Bib", "Wind Vest"],
        "brands": ["Fabrikam Active", "Proseware"],
        "basePrice": 70,
        "attributes": [
            ("size", "string", ["S", "M", "L", "XL"]),
            ("fit", "string", ["Relaxed", "Performance"]),
            ("waterproof", "boolean", [True, False]),
        ],
    },
    "Components": {
        "prefix": "CO",
        "nouns": ["Wheelset", "Brake Set", "Crankset", "Rear Derailleur"],
        "brands": ["Tailspin Components", "Wide World Imports"],
        "basePrice": 180,
        "attributes": [
            ("material", "string", ["Alloy", "Carbon Fiber", "Steel"]),
            ("speeds", "number", [10, 11, 12]),
            ("discipline", "string", ["Road", "Trail", "Gravel"]),
        ],
    },
    "Nutrition": {
        "prefix": "NU",
        "nouns": ["Energy Gel", "Hydration Mix", "Protein Bar", "Recovery Drink"],
        "brands": ["Litware Nutrition", "Consolidated Messenger"],
        "basePrice": 12,
        "attributes": [
            ("flavor", "string", ["Citrus", "Berry", "Chocolate"]),
            ("servings", "number", [1, 6, 12, 20]),
            ("vegan", "boolean", [True, False]),
        ],
    },
}
preserved_products = {
    ("Bikes", 1): ("bike-100", "Trail Bike Pro", 1299.99),
    ("Accessories", 1): ("helmet-200", "Touring Helmet", 89.0),
    ("Camping", 1): ("tent-300", "Three Person Trek Tent", 249.5),
}

sample_products = []
historical_audits = []
for category_name, config in category_configs.items():
    for sequence in range(1, products_per_category + 1):
        preserved = preserved_products.get((category_name, sequence))
        product_id = preserved[0] if preserved else f"{config['prefix'].lower()}-{sequence:03d}"
        name = preserved[1] if preserved else f"{config['nouns'][(sequence - 1) % 4]} {sequence:02d}"
        current_price = (
            preserved[2]
            if preserved
            else round(config["basePrice"] * (0.8 + seed.random() * 0.8), 2)
        )
        attributes = [
            {"key": key, "type": value_type, "value": seed.choice(values)}
            for key, value_type, values in config["attributes"]
        ]
        has_history = sequence <= 5 and product_id != "helmet-200"
        version = 3 if has_history else 1
        sample_products.append(
            {
                "id": product_id,
                "docType": "product",
                "productId": product_id,
                "categoryName": category_name,
                "sku": f"{config['prefix']}-{sequence:04d}",
                "name": name,
                "brand": config["brands"][(sequence - 1) % len(config["brands"])],
                "currentPrice": current_price,
                "currency": "USD",
                "inventory": seed.randint(4, 96),
                "isActive": sequence % 19 != 0,
                "version": version,
                "updatedAt": "2026-09-09T00:00:00Z",
                "updatedBy": "jumpstart-seed",
                "attributes": attributes,
            }
        )
        if has_history:
            first_price = round(current_price * 0.90, 2)
            second_price = round(current_price * 0.96, 2)
            for audit_version, old_price, new_price, changed_at in (
                (2, first_price, second_price, "2026-07-15T00:00:00Z"),
                (3, second_price, current_price, "2026-08-15T00:00:00Z"),
            ):
                historical_audits.append(
                    {
                        "id": f"seed-price-{product_id}-v{audit_version}",
                        "docType": "priceChange",
                        "productId": product_id,
                        "categoryName": category_name,
                        "oldPrice": old_price,
                        "newPrice": new_price,
                        "currency": "USD",
                        "reason": "Deterministic historical price adjustment",
                        "requestedBy": "jumpstart-seed",
                        "productVersion": audit_version,
                        "changedAt": changed_at,
                    }
                )

for product in sample_products:
    try:
        container.create_item(product)
        print(f"Created {product['id']}")
    except Exception as error:
        if getattr(error, "status_code", None) == 409:
            print(f"Kept existing {product['id']}")
        else:
            raise

for audit in historical_audits:
    try:
        container.create_item(audit)
    except Exception as error:
        if getattr(error, "status_code", None) != 409:
            raise

print(
    f"Seed complete: {len(sample_products)} products and "
    f"{len(historical_audits)} historical price changes checked."
)

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
if len(products) < expected_product_count:
    raise RuntimeError(
        f"Catalog verification failed: expected at least {expected_product_count} "
        f"products, found {len(products)}."
    )

display(products)
print("Catalog ready. Continue in the generated SQL analytics endpoint.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }