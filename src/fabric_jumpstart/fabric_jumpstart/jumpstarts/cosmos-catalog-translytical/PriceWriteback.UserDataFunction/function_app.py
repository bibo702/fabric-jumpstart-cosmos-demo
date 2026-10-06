"""Fabric User Data Function for validated catalog price write-back."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from azure.cosmos import CosmosClient
import fabric.functions as fn


COSMOS_URI = "{my-cosmos-artifact-uri}"
DATABASE_NAME = "{my-cosmos-database-name}"
CONTAINER_NAME = "SampleData"
MAX_BULK_UPDATES = 25
MAX_CHANGE_PERCENT = Decimal("30")

udf = fn.UserDataFunctions()


@dataclass(frozen=True)
class PriceUpdate:
    product_id: str
    category_name: str
    new_price: Decimal
    reason: str
    expected_version: int


class PriceUpdateError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_update(payload: dict[str, Any]) -> PriceUpdate:
    product_id = str(payload.get("productId", "")).strip()
    category_name = str(payload.get("categoryName", "")).strip()
    reason = str(payload.get("reason", "")).strip()

    if not product_id or not category_name:
        raise PriceUpdateError("invalid_identity", "Product and category are required.")
    if not reason:
        raise PriceUpdateError("missing_reason", "A reason is required.")
    if len(reason) > 200:
        raise PriceUpdateError("invalid_reason", "Reason must be 200 characters or fewer.")

    try:
        new_price = Decimal(str(payload["newPrice"]))
    except (KeyError, InvalidOperation, TypeError):
        raise PriceUpdateError("invalid_price", "Price must be a number.") from None
    if not new_price.is_finite() or new_price <= 0:
        raise PriceUpdateError("invalid_price", "Price must be finite and greater than zero.")

    expected_version = payload.get("expectedVersion")
    if (
        isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 1
    ):
        raise PriceUpdateError(
            "invalid_version",
            "Expected version must be a positive integer.",
        )

    return PriceUpdate(
        product_id=product_id,
        category_name=category_name,
        new_price=new_price,
        reason=reason,
        expected_version=expected_version,
    )


def build_mutation(
    product: dict[str, Any],
    update: PriceUpdate,
    *,
    requested_by: str,
    updated_at: str,
    max_change_percent: Decimal = MAX_CHANGE_PERCENT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if product.get("docType") != "product":
        raise PriceUpdateError("not_product", "The selected document is not a product.")
    if (
        product.get("id") != update.product_id
        or product.get("categoryName") != update.category_name
    ):
        raise PriceUpdateError(
            "identity_mismatch",
            "The product identity does not match the request.",
        )
    if product.get("isActive") is not True:
        raise PriceUpdateError("inactive_product", "Inactive products cannot be repriced.")
    if product.get("version") != update.expected_version:
        raise PriceUpdateError(
            "version_conflict",
            "The product changed after it was selected.",
        )

    try:
        current_price = Decimal(str(product["currentPrice"]))
    except (KeyError, InvalidOperation, TypeError):
        raise PriceUpdateError(
            "invalid_current_price",
            "The product has an invalid current price.",
        ) from None
    if not current_price.is_finite() or current_price <= 0:
        raise PriceUpdateError(
            "invalid_current_price",
            "The product has an invalid current price.",
        )

    change_percent = abs(update.new_price - current_price) / current_price * Decimal("100")
    if change_percent > max_change_percent:
        raise PriceUpdateError(
            "change_limit_exceeded",
            f"Price change exceeds the {max_change_percent.normalize()}% limit.",
        )

    next_version = update.expected_version + 1
    patch_operations = [
        {"op": "replace", "path": "/currentPrice", "value": float(update.new_price)},
        {"op": "replace", "path": "/version", "value": next_version},
        {"op": "replace", "path": "/updatedAt", "value": updated_at},
        {"op": "replace", "path": "/updatedBy", "value": requested_by},
    ]
    audit_document = {
        "id": f"price-{update.product_id}-v{next_version}",
        "docType": "priceChange",
        "productId": update.product_id,
        "categoryName": update.category_name,
        "oldPrice": float(current_price),
        "newPrice": float(update.new_price),
        "reason": update.reason,
        "requestedBy": requested_by,
        "appliedAt": updated_at,
        "productVersion": next_version,
    }
    return patch_operations, audit_document


def parse_bulk_updates(payloads: Iterable[dict[str, Any]]) -> list[PriceUpdate]:
    payload_list = list(payloads)
    if not payload_list:
        raise PriceUpdateError("empty_request", "At least one price update is required.")
    if len(payload_list) > MAX_BULK_UPDATES:
        raise PriceUpdateError(
            "bulk_limit_exceeded",
            f"A maximum of {MAX_BULK_UPDATES} products can be updated at once.",
        )

    updates = [parse_update(payload) for payload in payload_list]
    identities = [(update.category_name, update.product_id) for update in updates]
    if len(identities) != len(set(identities)):
        raise PriceUpdateError(
            "duplicate_product",
            "Each product can appear only once per request.",
        )
    return updates


def apply_update(
    container: Any,
    payload: dict[str, Any],
    *,
    requested_by: str,
    updated_at: str | None = None,
    max_change_percent: Decimal = MAX_CHANGE_PERCENT,
) -> dict[str, Any]:
    try:
        update = parse_update(payload)
        product = container.read_item(
            item=update.product_id,
            partition_key=update.category_name,
        )
        applied_at = updated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        operations, audit = build_mutation(
            product,
            update,
            requested_by=requested_by,
            updated_at=applied_at,
            max_change_percent=max_change_percent,
        )
        etag = product.get("_etag")
        if not etag:
            raise PriceUpdateError(
                "missing_etag",
                "The product does not include concurrency metadata.",
            )

        container.execute_item_batch(
            batch_operations=[
                ("patch", (update.product_id, operations), {"if_match_etag": etag}),
                ("create", (audit,), {}),
            ],
            partition_key=update.category_name,
        )
        return {
            "productId": update.product_id,
            "categoryName": update.category_name,
            "status": "applied",
            "version": audit["productVersion"],
            "message": "Price updated.",
        }
    except PriceUpdateError as error:
        status = "conflict" if error.code == "version_conflict" else "rejected"
        return {
            "productId": str(payload.get("productId", "")),
            "categoryName": str(payload.get("categoryName", "")),
            "status": status,
            "code": error.code,
            "message": str(error),
        }
    except Exception as error:
        if getattr(error, "status_code", None) in {409, 412}:
            return {
                "productId": str(payload.get("productId", "")),
                "categoryName": str(payload.get("categoryName", "")),
                "status": "conflict",
                "code": "concurrent_update",
                "message": "The product changed while the update was being applied.",
            }
        return {
            "productId": str(payload.get("productId", "")),
            "categoryName": str(payload.get("categoryName", "")),
            "status": "failed",
            "code": "write_failed",
            "message": "The price update could not be applied.",
        }


def apply_updates(
    container: Any,
    payloads: Iterable[dict[str, Any]],
    *,
    requested_by: str,
) -> list[dict[str, Any]]:
    payload_list = list(payloads)
    if not payload_list:
        raise PriceUpdateError("empty_request", "At least one price update is required.")
    if len(payload_list) > MAX_BULK_UPDATES:
        raise PriceUpdateError(
            "bulk_limit_exceeded",
            f"A maximum of {MAX_BULK_UPDATES} products can be updated at once.",
        )

    results = []
    seen = set()
    for payload in payload_list:
        identity = (
            str(payload.get("categoryName", "")).strip(),
            str(payload.get("productId", "")).strip(),
        )
        if identity in seen:
            results.append(
                {
                    "productId": identity[1],
                    "categoryName": identity[0],
                    "status": "rejected",
                    "code": "duplicate_product",
                    "message": "Each product can appear only once per request.",
                }
            )
            continue
        seen.add(identity)
        results.append(apply_update(container, payload, requested_by=requested_by))
    return results


@udf.connection(
    argName="cosmosClient",
    audienceType="CosmosDB",
    cosmos_endpoint=COSMOS_URI,
)
@udf.function()
def update_prices(
    cosmosClient: CosmosClient,
    updates: list[dict[str, Any]],
    requestedBy: str,
) -> list[dict[str, Any]]:
    """Validate and apply bounded, audited catalog price updates."""
    container = (
        cosmosClient.get_database_client(DATABASE_NAME)
        .get_container_client(CONTAINER_NAME)
    )
    return apply_updates(container, updates, requested_by=requestedBy)