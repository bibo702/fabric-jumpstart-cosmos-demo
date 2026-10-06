import json
from pathlib import Path

import yaml


PACKAGE_ROOT = (
    Path(__file__).parent.parent
    / "fabric_jumpstart"
    / "jumpstarts"
    / "cosmos-catalog-translytical"
)
REGISTRY_FILE = (
    Path(__file__).parent.parent
    / "fabric_jumpstart"
    / "jumpstarts"
    / "community"
    / "cosmos-catalog-translytical.yml"
)


def test_initial_package_is_explicitly_unlisted_and_deployable():
    config = yaml.safe_load(REGISTRY_FILE.read_text(encoding="utf-8"))
    item_paths = sorted(
        path for path in PACKAGE_ROOT.iterdir() if path.is_dir() and "." in path.name
    )

    assert {path.name for path in item_paths} == {
        "00_CosmosCatalogSetup.Notebook",
        "01_CosmosCatalogWriteback.Notebook",
        "PriceWriteback.UserDataFunction",
    }
    assert config["entry_point"] == "00_CosmosCatalogSetup.Notebook"
    assert config["include_in_listing"] is False
    assert config["items_in_scope"] == ["Notebook", "UserDataFunction"]
    assert config["cosmos_database"] == {
        "display_name": "cosmos db jumpstart",
        "description": "Operational product catalog for the Cosmos Catalog Jumpstart.",
        "definition_path": "_provisioning/cosmos-definition.json",
    }
    assert config["type"] == "Demo"
    assert "Power BI" not in config["workload_tags"]


def test_notebook_manifest_and_connected_setup_are_consistent():
    notebook = PACKAGE_ROOT / "00_CosmosCatalogSetup.Notebook"
    platform = json.loads((notebook / ".platform").read_text(encoding="utf-8"))
    content = (notebook / "notebook-content.py").read_text(encoding="utf-8")

    assert platform["metadata"]["type"] == "Notebook"
    assert platform["metadata"]["displayName"] == "00_CosmosCatalogSetup"
    assert "%pip install azure-cosmos==4.16.4" in content
    assert '"tags": ["parameters"]' in content
    assert 'cosmos_endpoint = "{my-cosmos-artifact-uri}"' in content
    assert 'database_name = "{my-cosmos-database-name}"' in content
    assert 'container_name = "SampleData"' in content
    assert "get_container_client(container_name)" in content
    assert "create_container_if_not_exists" not in content
    assert 'notebookutils.credentials.getToken("https://cosmos.azure.com/.default")' in content
    assert "create_item(product)" in content
    assert "## Acceptance test" in content
    assert "status: applied" in content
    assert "status: conflict" in content
    assert "saveAsTable" not in content
    assert "account_key" not in content.lower()
    assert "connection_string" not in content.lower()


def test_guided_writeback_notebook_invokes_the_published_function():
    notebook = PACKAGE_ROOT / "01_CosmosCatalogWriteback.Notebook"
    platform = json.loads((notebook / ".platform").read_text(encoding="utf-8"))
    content = (notebook / "notebook-content.py").read_text(encoding="utf-8")

    assert platform["metadata"]["type"] == "Notebook"
    assert platform["metadata"]["displayName"] == "01_CosmosCatalogWriteback"
    assert "%pip install azure-cosmos==4.16.4" in content
    assert 'cosmos_endpoint = "{my-cosmos-artifact-uri}"' in content
    assert 'database_name = "{my-cosmos-database-name}"' in content
    assert 'container_name = "SampleData"' in content
    assert 'udf_item_name = "PriceWriteback"' in content
    assert '"tags": ["parameters"]' in content
    assert "notebookutils.udf.getFunctions(udf_item_name)" in content
    assert "price_functions.update_prices(" in content
    assert "updates=[payload]" in content
    assert "requestedBy=requested_by.value" in content
    assert "widgets.Dropdown" in content
    assert "widgets.Button" in content
    assert "widgets.HTML" in content
    assert "widgets.Output" not in content
    assert "container.query_items(" in content
    assert {"applied", "rejected", "conflict"} <= set(content.split('"'))
    for direct_write in (
        "create_item(",
        "upsert_item(",
        "patch_item(",
        "execute_item_batch(",
    ):
        assert direct_write not in content


def test_cosmos_database_definition_creates_sample_container():
    definition = json.loads(
        (PACKAGE_ROOT / "_provisioning" / "cosmos-definition.json").read_text(
            encoding="utf-8"
        )
    )

    assert definition["$schema"].endswith("/CosmosDB/2.0.0/schema.json")
    assert len(definition["containers"]) == 1
    container = definition["containers"][0]
    assert container["options"]["autoscaleSettings"]["maxThroughput"] == 1000
    assert container["resource"]["id"] == "SampleData"
    assert container["resource"]["partitionKey"] == {
        "paths": ["/categoryName"],
        "kind": "Hash",
        "version": 2,
        "systemKey": False,
    }


def test_catalog_samples_demonstrate_flexible_attributes():
    content = (
        PACKAGE_ROOT / "00_CosmosCatalogSetup.Notebook" / "notebook-content.py"
    ).read_text(encoding="utf-8")
    sample_content = content.split("sample_products = [", 1)[1].split(
        "for product in sample_products", 1
    )[0]

    assert '"categoryName": "Bikes"' in sample_content
    assert '"categoryName": "Accessories"' in sample_content
    assert '"categoryName": "Camping"' in sample_content
    assert sample_content.count('"productId":') == 3
    assert sample_content.count('"attributes": [') == 3
    assert '"docType": "product"' in sample_content


def test_price_writeback_is_a_reusable_userdatafunction_export():
    function = PACKAGE_ROOT / "PriceWriteback.UserDataFunction"
    platform = json.loads((function / ".platform").read_text(encoding="utf-8"))
    definition = json.loads((function / "definition.json").read_text(encoding="utf-8"))
    resources = json.loads(
        (function / ".resources" / "functions.json").read_text(encoding="utf-8")
    )
    source = (function / "function_app.py").read_text(encoding="utf-8")

    assert platform["metadata"] == {
        "type": "UserDataFunction",
        "displayName": "PriceWriteback",
    }
    assert definition["runtime"] == "PYTHON"
    assert definition["connectedDataSources"] == []
    assert definition["functions"] == [
        {
            "name": "update_prices",
            "description": "Validate and apply bounded, audited catalog price updates.",
            "isPublicEndpointEnabled": True,
        }
    ]
    assert {library["name"] for library in definition["libraries"]["public"]} == {
        "azure-cosmos",
        "fabric-user-data-functions",
    }
    function_metadata = resources["functionsMetadata"][0]
    assert function_metadata["name"] == "update_prices"
    assert function_metadata["fabricProperties"]["fabricMetadataSchemaVersion"] == "1.1.0"
    assert function_metadata["fabricProperties"]["fabricFunctionParameters"][-1]["name"] == "requestedBy"
    assert 'COSMOS_URI = "{my-cosmos-artifact-uri}"' in source
    assert 'DATABASE_NAME = "{my-cosmos-database-name}"' in source
    assert 'CONTAINER_NAME = "SampleData"' in source
    assert 'audienceType="CosmosDB"' in source
    assert 'argName="cosmosClient"' in source
    assert "def apply_updates(" in source
    assert "from price_writeback import" not in source
    assert not (function / "price_writeback.py").exists()
    assert not (function / "resources" / "functions.json").exists()
    assert "msit-sql.cosmos.fabric.microsoft.com" not in source