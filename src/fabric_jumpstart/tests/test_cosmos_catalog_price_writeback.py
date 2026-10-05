from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest


MODULE_PATH = (
    Path(__file__).parent.parent
    / "fabric_jumpstart"
    / "jumpstarts"
    / "cosmos-catalog-translytical"
    / "PriceWriteback.UserDataFunction"
    / "function_app.py"
)


class StubUserDataFunctions:
    def connection(self, **_kwargs):
        return lambda function: function

    def function(self):
        return lambda function: function


class StubCosmosClient:
    pass


azure_module = ModuleType("azure")
azure_cosmos_module = ModuleType("azure.cosmos")
setattr(azure_cosmos_module, "CosmosClient", StubCosmosClient)
setattr(azure_module, "cosmos", azure_cosmos_module)
fabric_module = ModuleType("fabric")
fabric_functions_module = ModuleType("fabric.functions")
setattr(fabric_functions_module, "UserDataFunctions", StubUserDataFunctions)
setattr(fabric_module, "functions", fabric_functions_module)

runtime_stubs = {
    "azure": azure_module,
    "azure.cosmos": azure_cosmos_module,
    "fabric": fabric_module,
    "fabric.functions": fabric_functions_module,
}
original_modules = {name: sys.modules.get(name) for name in runtime_stubs}
sys.modules.update(runtime_stubs)

SPEC = spec_from_file_location("cosmos_catalog_price_writeback", MODULE_PATH)
assert SPEC and SPEC.loader
price_writeback = module_from_spec(SPEC)
sys.modules[SPEC.name] = price_writeback
try:
    SPEC.loader.exec_module(price_writeback)
finally:
    for name, original_module in original_modules.items():
        if original_module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original_module

PriceUpdateError = price_writeback.PriceUpdateError


def request(**overrides):
    payload = {
        "productId": "bike-100",
        "categoryName": "Bikes",
        "newPrice": 1199.99,
        "reason": "Seasonal promotion",
        "expectedVersion": 3,
    }
    payload.update(overrides)
    return payload


def product(**overrides):
    document = {
        "id": "bike-100",
        "docType": "product",
        "categoryName": "Bikes",
        "currentPrice": 1299.99,
        "isActive": True,
        "version": 3,
        "_etag": "etag-v3",
    }
    document.update(overrides)
    return document


def test_builds_versioned_product_patch_and_immutable_audit_document():
    update = price_writeback.parse_update(request())

    operations, audit = price_writeback.build_mutation(
        product(),
        update,
        requested_by="analyst@contoso.com",
        updated_at="2026-09-09T12:00:00Z",
    )

    assert {operation["path"]: operation["value"] for operation in operations} == {
        "/currentPrice": 1199.99,
        "/version": 4,
        "/updatedAt": "2026-09-09T12:00:00Z",
        "/updatedBy": "analyst@contoso.com",
    }
    assert audit == {
        "id": "price-bike-100-v4",
        "docType": "priceChange",
        "productId": "bike-100",
        "categoryName": "Bikes",
        "oldPrice": 1299.99,
        "newPrice": 1199.99,
        "reason": "Seasonal promotion",
        "requestedBy": "analyst@contoso.com",
        "appliedAt": "2026-09-09T12:00:00Z",
        "productVersion": 4,
    }


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"newPrice": 0}, "invalid_price"),
        ({"newPrice": "NaN"}, "invalid_price"),
        ({"reason": ""}, "missing_reason"),
        ({"expectedVersion": True}, "invalid_version"),
    ],
)
def test_rejects_invalid_request_values(overrides, code):
    with pytest.raises(PriceUpdateError) as error:
        price_writeback.parse_update(request(**overrides))

    assert error.value.code == code


def test_rejects_stale_product_version():
    update = price_writeback.parse_update(request(expectedVersion=2))

    with pytest.raises(PriceUpdateError) as error:
        price_writeback.build_mutation(
            product(),
            update,
            requested_by="analyst@contoso.com",
            updated_at="2026-09-09T12:00:00Z",
        )

    assert error.value.code == "version_conflict"


def test_rejects_excessive_price_change():
    update = price_writeback.parse_update(request(newPrice=500))

    with pytest.raises(PriceUpdateError) as error:
        price_writeback.build_mutation(
            product(),
            update,
            requested_by="analyst@contoso.com",
            updated_at="2026-09-09T12:00:00Z",
            max_change_percent=Decimal("30"),
        )

    assert error.value.code == "change_limit_exceeded"


def test_rejects_duplicate_products_in_bulk_request():
    with pytest.raises(PriceUpdateError) as error:
        price_writeback.parse_bulk_updates([request(), request(newPrice=1099)])

    assert error.value.code == "duplicate_product"


def test_rejects_bulk_request_over_limit():
    payloads = [
        request(productId=f"bike-{index}", categoryName="Bikes")
        for index in range(price_writeback.MAX_BULK_UPDATES + 1)
    ]

    with pytest.raises(PriceUpdateError) as error:
        price_writeback.parse_bulk_updates(payloads)

    assert error.value.code == "bulk_limit_exceeded"


class StubContainer:
    def __init__(self, document, error=None):
        self.document = document
        self.error = error
        self.batch = None

    def read_item(self, *, item, partition_key):
        assert item == self.document["id"]
        assert partition_key == self.document["categoryName"]
        return self.document

    def execute_item_batch(self, *, batch_operations, partition_key):
        if self.error:
            raise self.error
        self.batch = (batch_operations, partition_key)
        return [{"statusCode": 200}, {"statusCode": 201}]


def test_applies_patch_and_audit_in_one_etag_conditioned_batch():
    container = StubContainer(product())

    result = price_writeback.apply_update(
        container,
        request(),
        requested_by="analyst@contoso.com",
        updated_at="2026-09-09T12:00:00Z",
    )

    assert container.batch is not None
    operations, partition_key = container.batch
    assert partition_key == "Bikes"
    assert operations[0][0] == "patch"
    assert operations[0][2] == {"if_match_etag": "etag-v3"}
    assert operations[1][0] == "create"
    assert operations[1][1][0]["docType"] == "priceChange"
    assert result["status"] == "applied"
    assert result["version"] == 4


def test_maps_etag_batch_failure_to_sanitized_conflict():
    class ConflictError(RuntimeError):
        status_code = 412

    conflict = ConflictError("sensitive service detail")
    container = StubContainer(product(), error=conflict)

    result = price_writeback.apply_update(
        container,
        request(),
        requested_by="analyst@contoso.com",
    )

    assert result == {
        "productId": "bike-100",
        "categoryName": "Bikes",
        "status": "conflict",
        "code": "concurrent_update",
        "message": "The product changed while the update was being applied.",
    }


def test_sanitizes_unexpected_storage_failure():
    container = StubContainer(product(), error=RuntimeError("credential was secret"))

    result = price_writeback.apply_update(
        container,
        request(),
        requested_by="analyst@contoso.com",
    )

    assert result["status"] == "failed"
    assert result["code"] == "write_failed"
    assert "secret" not in result["message"]


def test_bulk_returns_partial_success_for_invalid_and_duplicate_rows():
    container = StubContainer(product())

    results = price_writeback.apply_updates(
        container,
        [request(), request(productId="bad", categoryName="Bikes", newPrice=0), request()],
        requested_by="analyst@contoso.com",
    )

    assert [result["status"] for result in results] == ["applied", "rejected", "rejected"]
    assert results[1]["code"] == "invalid_price"
    assert results[2]["code"] == "duplicate_product"