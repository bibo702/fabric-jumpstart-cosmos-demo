"""Fabric-facing adapters for the audited Product PIM APIs."""

import fabric.functions as fn
from fabric.functions.cosmosdb import get_cosmos_client

import backend


udf = fn.UserDataFunctions()
COSMOS_URI = "{my-cosmos-artifact-uri}"
DATABASE_NAME = "{my-cosmos-database-name}"
CONTAINER_NAME = "ProductPim"
SEARCH_CONTAINER_NAME = "ProductPimSearch"
PRINCIPAL_GRANTS: dict = {}


def invoke(cosmos_db, my_context, action, operation, *arguments) -> dict:
    try:
        actor = backend.caller_identity(my_context)
        for grant in (action,) if isinstance(action, str) else action:
            backend.authorize(actor, PRINCIPAL_GRANTS, grant)
        client = get_cosmos_client(cosmos_db, COSMOS_URI)
        container = client.get_database_client(DATABASE_NAME).get_container_client(
            CONTAINER_NAME
        )
        return operation(container, *arguments, my_context, PRINCIPAL_GRANTS)
    except backend.BackendError as error:
        return {"status": "rejected", "code": error.code, "message": str(error)}
    except Exception:
        return {
            "status": "failed",
            "code": "storage_error",
            "message": "The operation could not be completed. Retry mutations with the same operationId.",
        }


def invoke_search(cosmos_db, my_context, action, operation, *arguments) -> dict:
    try:
        actor = backend.caller_identity(my_context)
        for grant in (action,) if isinstance(action, str) else action:
            backend.authorize(actor, PRINCIPAL_GRANTS, grant)
        client = get_cosmos_client(cosmos_db, COSMOS_URI)
        database = client.get_database_client(DATABASE_NAME)
        catalog = database.get_container_client(CONTAINER_NAME)
        search = database.get_container_client(SEARCH_CONTAINER_NAME)
        return operation(
            catalog, search, *arguments, my_context, PRINCIPAL_GRANTS
        )
    except backend.BackendError as error:
        return {"status": "rejected", "code": error.code, "message": str(error)}
    except Exception:
        return {
            "status": "failed",
            "code": "storage_error",
            "message": "The search operation could not be completed.",
        }


def execute_product_search(
    _catalog,
    search,
    query_text,
    query_vector,
    page_size,
    status,
    my_context,
    grants,
):
    return backend.search_products(
        search,
        query_text,
        query_vector,
        page_size,
        status,
        my_context,
        grants,
    )


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.function()
def update_product(
    cosmosDb: fn.FabricItem, myContext: fn.UserDataFunctionContext, payload: dict
) -> dict:
    return invoke(cosmosDb, myContext, "write", backend.apply_update, payload)


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.function()
def get_product(
    cosmosDb: fn.FabricItem, myContext: fn.UserDataFunctionContext, productId: str
) -> dict:
    return invoke(cosmosDb, myContext, "read", backend.get_product, productId)


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.function()
def get_history(
    cosmosDb: fn.FabricItem,
    myContext: fn.UserDataFunctionContext,
    productId: str,
    pageSize: int,
    continuationToken: str,
) -> dict:
    return invoke(
        cosmosDb,
        myContext,
        "read",
        backend.get_history,
        productId,
        pageSize,
        continuationToken,
    )


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.function()
def seed_catalog(
    cosmosDb: fn.FabricItem, myContext: fn.UserDataFunctionContext
) -> dict:
    return invoke(cosmosDb, myContext, "seed", backend.seed_catalog)


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.function()
def list_products(
    cosmosDb: fn.FabricItem,
    myContext: fn.UserDataFunctionContext,
    pageSize: int,
    afterProductId: str,
) -> dict:
    return invoke(
        cosmosDb, myContext, "read", backend.list_products, pageSize, afterProductId
    )


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.function()
def index_product_search(
    cosmosDb: fn.FabricItem,
    myContext: fn.UserDataFunctionContext,
    payload: dict,
) -> dict:
    return invoke_search(
        cosmosDb,
        myContext,
        ("read", "write"),
        backend.index_product_search,
        payload,
    )


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.function()
def search_products(
    cosmosDb: fn.FabricItem,
    myContext: fn.UserDataFunctionContext,
    queryText: str,
    queryVector: list,
    pageSize: int,
    status: str,
) -> dict:
    return invoke_search(
        cosmosDb,
        myContext,
        "read",
        execute_product_search,
        queryText,
        queryVector,
        pageSize,
        status,
    )


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.function()
def index_search_query(
    cosmosDb: fn.FabricItem,
    myContext: fn.UserDataFunctionContext,
    payload: dict,
) -> dict:
    return invoke_search(
        cosmosDb,
        myContext,
        ("read", "write"),
        backend.index_search_query,
        payload,
    )


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.function()
def search_products_by_query(
    cosmosDb: fn.FabricItem,
    myContext: fn.UserDataFunctionContext,
    queryId: str,
    pageSize: int,
    status: str,
) -> dict:
    return invoke_search(
        cosmosDb,
        myContext,
        "read",
        backend.search_products_by_query,
        queryId,
        pageSize,
        status,
    )
