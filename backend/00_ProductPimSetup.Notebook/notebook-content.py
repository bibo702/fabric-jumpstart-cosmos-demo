# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {"name": "synapse_pyspark"},
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Cosmos Product PIM: Backend Setup and Acceptance
#
# Configure the Cosmos database, the `/productId`-partitioned `ProductPim`
# container, and `ProductPimBackend` using the backend README before running.
# Search indexing is handled by notebooks 01/02; Rayfin is
# deployed separately. This notebook validates the operational Cosmos contracts.
#
# ## Before running
#
# Use a capacity-backed workspace where Cosmos DB and User Data Functions are
# enabled. The publishing UDF owner needs database write access. Your invoking
# identity needs Fabric UDF execution access and explicit `read`, `write`, and
# `seed` backend grants configured in the UDF source. These are separate gates.
# Open the deployed UDF, verify Library management includes the private backend
# wheel, and publish it if Fabric shows unpublished changes.
#
# Run this notebook interactively, one cell at a time. Nothing runs it
# automatically. No account keys or database SDK are needed in this notebook:
# every read and write goes through the published UDF.
#
# **Data changes:** seeding adds three synthetic products, six reviews and three
# creation events when absent. Acceptance changes and then restores the bike
# description and creates one uniquely named acceptance product per run. That
# product is archived/restored to validate status changes. It preserves history.

# CELL ********************

udf_item_name = "ProductPimBackend"
database_name = "{my-cosmos-database-name}"
product_id = "bike-100"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "tags": ["parameters"]
# META }

# CELL ********************

import json
from uuid import UUID, uuid4

import notebookutils
from IPython.display import Markdown, display

pim = notebookutils.udf.getFunctions(udf_item_name)
item_details = pim.itemDetails
if isinstance(item_details, str):
    item_details = json.loads(item_details)
workspace_id = str(UUID(item_details["WorkspaceId"]))
udf_id = str(UUID(item_details["Id"]))
display(Markdown(
    f"[Open backend](https://app.fabric.microsoft.com/groups/{workspace_id}/userdatafunctions/{udf_id})"
    f" | Database: **{database_name}**, container: **ProductPim**"
))
display(pim.functionDetails)


def result_object(value):
    result = json.loads(value) if isinstance(value, str) else value
    assert isinstance(result, dict), "Expected a UDF JSON object"
    assert result.get("status") not in {"failed", "rejected"}, result
    return result


def rejected_code(value):
    result = json.loads(value) if isinstance(value, str) else value
    assert result.get("status") == "rejected", result
    return result["code"]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Seed twice
#
# First run: three `created` results in a fresh database. Existing products are
# `skipped`. The second call must skip all three. After initialization, remove
# the `seed` role only after notebook 01 has initialized the larger search demo,
# then redeploy with `update_existing=True`. Skip this seed cell on later runs.

# CELL ********************

first_seed = result_object(pim.seed_catalog())
second_seed = result_object(pim.seed_catalog())
assert len(first_seed["items"]) == 3, first_seed
assert all(item["status"] in {"created", "skipped"} for item in first_seed["items"])
assert len(second_seed["items"]) == 3, second_seed
assert all(item["status"] == "skipped" for item in second_seed["items"])
display(first_seed)
display(second_seed)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Read and prepare one change
#
# The current version is read on every run. Do not run this cell again to retry
# an uncertain write: rerun the next cell with the same `payload` instead.
# The verified caller is supplied by Fabric, never by this payload.

# CELL ********************

before = result_object(pim.get_product(productId=product_id))
assert before["status"] == "active", "Restore this product before running acceptance"
payload = {
    "productId": product_id,
    "expectedVersion": before["version"],
    "operationId": str(uuid4()),
    "changes": {"description": f"Backend acceptance test {uuid4()}"},
    "reason": "Validate v2 product mutation, audit and retry contracts",
}
display(before)
display(payload)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

applied = result_object(pim.update_product(payload=payload))
assert applied["status"] == "applied", applied
assert applied["version"] == before["version"] + 1, applied
replay = result_object(pim.update_product(payload=payload))
assert replay["replayed"] is True, replay
assert replay["eventId"] == applied["eventId"], replay
after = result_object(pim.get_product(productId=product_id))
assert after["version"] == applied["version"], after
assert after["description"] == payload["changes"]["description"], after
display(applied)
display(replay)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Reject reused operation IDs and stale versions
#
# These two requests must not change the product or create another audit event.

# CELL ********************

changed_request = {**payload, "reason": "Different request with the same operation ID"}
assert rejected_code(pim.update_product(payload=changed_request)) == "operation_conflict"
stale_request = {**payload, "operationId": str(uuid4())}
assert rejected_code(pim.update_product(payload=stale_request)) == "version_conflict"
unchanged = result_object(pim.get_product(productId=product_id))
assert unchanged["version"] == after["version"], unchanged

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Inspect paged audit history
#
# This checks that exactly one event exists for the update and its old/new values
# match. Confirm the displayed `actor.tenantId` and `actor.oid` against your Entra
# identity. They must describe the invoker, not merely the UDF publishing owner.

# CELL ********************

events = []
continuation = ""
seen_tokens = set()
for page_number in range(1000):
    page = result_object(pim.get_history(
        productId=product_id, pageSize=2, continuationToken=continuation
    ))
    events.extend(page["items"])
    continuation = page["continuationToken"]
    if not continuation:
        break
    assert continuation not in seen_tokens, "History pagination repeated a token"
    seen_tokens.add(continuation)
else:
    raise RuntimeError("History exceeded the acceptance notebook's 1000-page limit")
matching_events = [event for event in events if event["id"] == applied["eventId"]]
assert len(matching_events) == 1, matching_events
event = matching_events[0]
assert event["fromVersion"] == before["version"], event
assert event["toVersion"] == after["version"], event
assert event["changes"] == [{
    "path": "/description", "oldValue": before["description"],
    "newValue": after["description"],
}], event
assert event["actor"] == after["updatedBy"], event
assert UUID(event["actor"]["tenantId"]) and UUID(event["actor"]["oid"])
assert event["invocationId"], event
display(event)
print("PASS: seed, update, replay, conflicts and paged audit history")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Restore the original content, then create and archive/restore a product
#
# These operations retain their own audit events. The commercial price is an
# unconfigured zero-USD placeholder and remains read-only through this demo API.
# Each full run leaves one synthetic acceptance product; it never deletes history.

# CELL ********************

restored_content = result_object(pim.update_product(payload={
    "productId": product_id, "expectedVersion": after["version"],
    "operationId": str(uuid4()), "changes": {"description": before["description"]},
    "reason": "Restore original content after backend acceptance",
}))
assert restored_content["version"] == after["version"] + 1, restored_content
acceptance_id = f"acceptance-{uuid4().hex}"
creation = {
    "productId": acceptance_id, "operationId": str(uuid4()),
    "name": "Synthetic acceptance product", "categoryName": "Acceptance",
    "description": "Created by the operational Cosmos acceptance notebook.",
    "reason": "Verify atomic product creation",
}
created = result_object(pim.create_product(payload=creation))
assert created["status"] == "applied" and created["version"] == 1, created
replayed_creation = result_object(pim.create_product(payload=creation))
assert replayed_creation["replayed"] and replayed_creation["eventId"] == created["eventId"], replayed_creation
for expected_version, target_status in ((1, "deleted"), (2, "active")):
    status_update = result_object(pim.update_product(payload={
        "productId": acceptance_id, "expectedVersion": expected_version,
        "operationId": str(uuid4()), "changes": {"status": target_status},
        "reason": f"Acceptance status transition to {target_status}",
    }))
    current = result_object(pim.get_product(productId=acceptance_id))
    assert status_update["version"] == expected_version + 1, status_update
    assert current["status"] == target_status, current
creation_history = result_object(pim.get_history(
    productId=acceptance_id, pageSize=10, continuationToken="",
))
assert len(creation_history["items"]) == 3, creation_history
assert {event["action"] for event in creation_history["items"]} == {
    "ProductCreated", "ProductDeleted", "ProductRestored",
}, creation_history
print("PASS: atomic creation/retry, archive/restore, and original content restoration")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Complete the live security checks
#
# 1. Invoke `get_product(productId="bike-100")` as a second user with Fabric
#    invocation access but no backend grant. Expect `status: rejected`,
#    `code: forbidden`. No database access should be attempted for that caller.
# 2. Give a second approved user `read` and `write` grants through installation,
#    rerun acceptance as that user, and verify a different `actor.oid` in history.
# 3. From two sessions read the same version; submit different changes with
#    different operation IDs. Only one may apply. Verify the loser reports
#    `version_conflict` and no extra event exists for the losing request.
# 4. Review the container's `/productId` partition key and non-expiring audit and
#    operation documents. Application history is append-only; a privileged
#    database administrator can still change documents.
# 5. After notebook 01 has seeded the search dataset, remove `seed` permission
#    and redeploy the backend. Record outcomes before hosted app acceptance.
#    These checks are not proven by the
#    notebook's single-user PASS message.