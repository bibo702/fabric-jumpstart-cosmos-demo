# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Guided Catalog Price Write-back
#
# Use this notebook after publishing `PriceWriteback`. Select a product, enter a
# new price and business reason, and submit the change through the User Data
# Function. The notebook reads products directly from Cosmos DB, but all writes
# go through the validated and audited function.
#
# Result states:
#
# - `applied`: the price changed and an audit document was created.
# - `rejected`: validation failed; review the displayed reason.
# - `conflict`: the product changed since it was loaded; refresh and try again.
# - `failed`: the function could not apply the update.

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
udf_item_name = "PriceWriteback"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "tags": ["parameters"]
# META }

# CELL ********************

import html
import time

from azure.core.credentials import AccessToken, TokenCredential
from azure.cosmos import CosmosClient
from IPython.display import display
import ipywidgets as widgets
import notebookutils


class FabricTokenCredential(TokenCredential):
    def get_token(self, *scopes, **kwargs):
        token = notebookutils.credentials.getToken(
            "https://cosmos.azure.com/.default"
        )
        return AccessToken(token, int(time.time()) + 3000)


client = CosmosClient(cosmos_endpoint, credential=FabricTokenCredential())
container = (
    client.get_database_client(database_name)
    .get_container_client(container_name)
)
price_functions = notebookutils.udf.getFunctions(udf_item_name)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

products_by_key = {}

product_selector = widgets.Dropdown(description="Product", layout=widgets.Layout(width="620px"))
product_details = widgets.HTML()
new_price = widgets.BoundedFloatText(
    description="New price",
    min=0.01,
    max=1000000000,
    step=0.01,
)
reason = widgets.Textarea(
    description="Reason",
    placeholder="Why is this price changing?",
    layout=widgets.Layout(width="620px", height="80px"),
)
requested_by = widgets.Text(
    value=str(notebookutils.runtime.context["userName"]),
    description="Requested by",
    layout=widgets.Layout(width="620px"),
)
refresh_button = widgets.Button(description="Refresh products", icon="refresh")
submit_button = widgets.Button(
    description="Submit price change",
    button_style="primary",
    icon="check",
)
status_panel = widgets.HTML(
    value="<div style='padding:10px;border-left:4px solid #605e5c'>Ready.</div>"
)


def render_status(status, message, code=""):
    colors = {
        "applied": ("#107c10", "Applied"),
        "rejected": ("#a4262c", "Rejected"),
        "conflict": ("#ca5010", "Conflict"),
        "failed": ("#a4262c", "Failed"),
        "working": ("#0078d4", "Working"),
    }
    color, label = colors.get(status, ("#605e5c", status.title()))
    code_text = f" <code>{html.escape(str(code))}</code>" if code else ""
    status_panel.value = (
        f"<div style='padding:10px;border-left:4px solid {color}'>"
        f"<strong>{html.escape(label)}</strong>{code_text}<br>"
        f"{html.escape(str(message))}</div>"
    )


def selected_product():
    return products_by_key.get(product_selector.value)


def show_selected_product(*_):
    product = selected_product()
    if not product:
        product_details.value = "<em>No product selected.</em>"
        return
    new_price.value = float(product["currentPrice"])
    product_details.value = (
        "<div style='padding:10px 0'>"
        f"<strong>{html.escape(str(product['name']))}</strong> "
        f"({html.escape(str(product['sku']))})<br>"
        f"Current price: <strong>{float(product['currentPrice']):,.2f} "
        f"{html.escape(str(product['currency']))}</strong> | "
        f"Version: <strong>{int(product['version'])}</strong> | "
        f"Category: {html.escape(str(product['categoryName']))}"
        "</div>"
    )


def refresh_products(_=None):
    global products_by_key
    render_status("working", "Loading the current catalog from Cosmos DB...")
    products = sorted(
        container.query_items(
            query="SELECT * FROM c WHERE c.docType = 'product'",
            enable_cross_partition_query=True,
        ),
        key=lambda product: (product["categoryName"], product["name"]),
    )
    products_by_key = {
        f"{product['categoryName']}::{product['productId']}": product
        for product in products
    }
    product_selector.options = [
        (
            f"{product['categoryName']} | {product['name']} | "
            f"{float(product['currentPrice']):,.2f} {product['currency']}",
            f"{product['categoryName']}::{product['productId']}",
        )
        for product in products
    ]
    show_selected_product()
    render_status("ready", f"Loaded {len(products)} products.")


def submit_price_change(_):
    product = selected_product()
    if not product:
        render_status("rejected", "Select a product before submitting.", "missing_product")
        return

    payload = {
        "productId": product["productId"],
        "categoryName": product["categoryName"],
        "newPrice": new_price.value,
        "reason": reason.value,
        "expectedVersion": product["version"],
    }
    submit_button.disabled = True
    render_status("working", "Submitting the validated price change...")
    try:
        results = price_functions.update_prices(
            updates=[payload],
            requestedBy=requested_by.value,
        )
        result = results[0]
        status = result.get("status", "failed")
        message = result.get("message", "The function returned no message.")
        if status == "conflict":
            message = f"{message} Refresh products before trying again."
        render_status(status, message, result.get("code", ""))
        if status == "applied":
            reason.value = ""
        refresh_products()
        render_status(status, message, result.get("code", ""))
    except Exception as error:
        render_status("failed", f"Function invocation failed: {error}", "invocation_failed")
    finally:
        submit_button.disabled = False


product_selector.observe(show_selected_product, names="value")
refresh_button.on_click(refresh_products)
submit_button.on_click(submit_price_change)

display(
    widgets.VBox(
        [
            widgets.HTML("<h2>Catalog price write-back</h2>"),
            product_selector,
            product_details,
            new_price,
            reason,
            requested_by,
            widgets.HBox([refresh_button, submit_button]),
            status_panel,
        ]
    )
)
refresh_products()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }