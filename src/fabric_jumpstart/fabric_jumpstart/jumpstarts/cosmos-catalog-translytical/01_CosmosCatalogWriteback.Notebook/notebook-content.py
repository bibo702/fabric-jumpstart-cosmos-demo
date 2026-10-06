# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Guided Catalog Price Write-back
#
# Use this notebook after publishing `PriceWriteback`. Filter the catalog, select
# up to 25 products, enter a percentage adjustment and business reason, and submit
# the changes through the User Data Function. The notebook reads products and
# audit history directly from Cosmos DB, but all writes go through the validated
# and audited function.
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

MAX_BULK_UPDATES = 25
all_products = []
products_by_key = {}

category_filter = widgets.Dropdown(
    description="Category",
    layout=widgets.Layout(width="620px"),
)
product_selector = widgets.SelectMultiple(
    description="Products",
    rows=10,
    layout=widgets.Layout(width="760px"),
)
product_details = widgets.HTML(value="<em>No products selected.</em>")
adjustment_percent = widgets.BoundedFloatText(
    description="Adjust %",
    min=-30,
    max=30,
    step=0.5,
    value=5,
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
    description="Apply price changes",
    button_style="primary",
    icon="check",
)
audit_refresh_button = widgets.Button(description="Refresh audit history", icon="history")
audit_history = widgets.HTML()
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


def selected_products():
    return [
        products_by_key[key]
        for key in product_selector.value
        if key in products_by_key
    ]


def show_selected_products(*_):
    products = selected_products()
    if not products:
        product_details.value = "<em>No products selected.</em>"
        return
    rows = []
    adjustment = 1 + adjustment_percent.value / 100
    for product in products:
        proposed_price = round(float(product["currentPrice"]) * adjustment, 2)
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(product['name']))}</td>"
            f"<td>{html.escape(str(product['categoryName']))}</td>"
            f"<td>{float(product['currentPrice']):,.2f}</td>"
            f"<td><strong>{proposed_price:,.2f}</strong></td>"
            f"<td>{int(product['version'])}</td>"
            "</tr>"
        )
    product_details.value = (
        f"<p><strong>{len(products)} of {MAX_BULK_UPDATES}</strong> products selected.</p>"
        "<table style='border-collapse:collapse;width:100%'>"
        "<thead><tr><th align='left'>Product</th><th align='left'>Category</th>"
        "<th align='right'>Current</th><th align='right'>Proposed</th>"
        "<th align='right'>Version</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def filter_products(*_):
    category = category_filter.value
    filtered_products = [
        product
        for product in all_products
        if not category or product["categoryName"] == category
    ]
    product_selector.options = [
        (
            f"{product['name']} | {float(product['currentPrice']):,.2f} "
            f"{product['currency']} | v{product['version']}",
            f"{product['categoryName']}::{product['productId']}",
        )
        for product in filtered_products
    ]
    product_selector.value = ()
    show_selected_products()


def refresh_products(_=None):
    global all_products, products_by_key
    render_status("working", "Loading the current catalog from Cosmos DB...")
    all_products = sorted(
        container.query_items(
            query="SELECT * FROM c WHERE c.docType = 'product'",
            enable_cross_partition_query=True,
        ),
        key=lambda product: (product["categoryName"], product["name"]),
    )
    products_by_key = {
        f"{product['categoryName']}::{product['productId']}": product
        for product in all_products
    }
    categories = sorted({product["categoryName"] for product in all_products})
    previous_category = category_filter.value
    category_filter.options = [("All categories", "")] + [
        (category, category) for category in categories
    ]
    category_filter.value = previous_category if previous_category in categories else ""
    filter_products()
    render_status("ready", f"Loaded {len(all_products)} products.")


def refresh_audit_history(_=None):
    audits = sorted(
        container.query_items(
            query="SELECT * FROM c WHERE c.docType = 'priceChange'",
            enable_cross_partition_query=True,
        ),
        key=lambda audit: audit.get("changedAt", ""),
        reverse=True,
    )[:25]
    if not audits:
        audit_history.value = "<em>No price changes recorded yet.</em>"
        return
    rows = [
        "<tr>"
        f"<td>{html.escape(str(audit.get('changedAt', '')))}</td>"
        f"<td>{html.escape(str(audit.get('productId', '')))}</td>"
        f"<td>{html.escape(str(audit.get('categoryName', '')))}</td>"
        f"<td>{float(audit.get('oldPrice', 0)):,.2f}</td>"
        f"<td>{float(audit.get('newPrice', 0)):,.2f}</td>"
        f"<td>{html.escape(str(audit.get('requestedBy', '')))}</td>"
        f"<td>{html.escape(str(audit.get('reason', '')))}</td>"
        "</tr>"
        for audit in audits
    ]
    audit_history.value = (
        "<table style='border-collapse:collapse;width:100%'>"
        "<thead><tr><th align='left'>Changed</th><th align='left'>Product</th>"
        "<th align='left'>Category</th><th align='right'>Old</th>"
        "<th align='right'>New</th><th align='left'>Requested by</th>"
        "<th align='left'>Reason</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def submit_price_change(_):
    products = selected_products()
    if not products:
        render_status("rejected", "Select at least one product.", "missing_product")
        return
    if len(products) > MAX_BULK_UPDATES:
        render_status(
            "rejected",
            f"Select no more than {MAX_BULK_UPDATES} products.",
            "too_many_updates",
        )
        return
    if adjustment_percent.value == 0:
        render_status("rejected", "Enter a non-zero percentage adjustment.", "no_change")
        return

    multiplier = 1 + adjustment_percent.value / 100
    payloads = [
        {
            "productId": product["productId"],
            "categoryName": product["categoryName"],
            "newPrice": round(float(product["currentPrice"]) * multiplier, 2),
            "reason": reason.value,
            "expectedVersion": product["version"],
        }
        for product in products
    ]
    submit_button.disabled = True
    render_status("working", f"Submitting {len(payloads)} validated price changes...")
    try:
        results = price_functions.update_prices(
            updates=payloads,
            requestedBy=requested_by.value,
        )
        counts = {
            status: sum(result.get("status") == status for result in results)
            for status in ("applied", "rejected", "conflict", "failed")
        }
        status = "applied" if counts["applied"] == len(results) else "failed"
        message = ", ".join(
            f"{count} {result_status}"
            for result_status, count in counts.items()
            if count
        )
        if counts["applied"]:
            reason.value = ""
        refresh_products()
        refresh_audit_history()
        render_status(status, message)
    except Exception as error:
        render_status("failed", f"Function invocation failed: {error}", "invocation_failed")
    finally:
        submit_button.disabled = False


category_filter.observe(filter_products, names="value")
product_selector.observe(show_selected_products, names="value")
adjustment_percent.observe(show_selected_products, names="value")
refresh_button.on_click(refresh_products)
audit_refresh_button.on_click(refresh_audit_history)
submit_button.on_click(submit_price_change)

display(
    widgets.VBox(
        [
            widgets.HTML("<h2>Catalog price write-back</h2>"),
            category_filter,
            product_selector,
            product_details,
            adjustment_percent,
            reason,
            requested_by,
            widgets.HBox([refresh_button, submit_button]),
            status_panel,
            widgets.HTML("<h2>Recent price-change audit history</h2>"),
            audit_refresh_button,
            audit_history,
        ]
    )
)
refresh_products()
refresh_audit_history()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }