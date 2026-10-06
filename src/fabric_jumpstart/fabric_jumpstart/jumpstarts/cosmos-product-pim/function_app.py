"""Fabric-facing adapters for the audited product and AI proposal APIs."""

import fabric.functions as fn
from fabric.functions.cosmosdb import get_cosmos_client

import backend


udf = fn.UserDataFunctions()
COSMOS_URI = "{my-cosmos-artifact-uri}"
DATABASE_NAME = "{my-cosmos-database-name}"
CONTAINER_NAME = "ProductPim"
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
def get_reviews(
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
        backend.get_documents,
        productId,
        "review",
        pageSize,
        continuationToken,
    )


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.function()
def get_proposals(
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
        backend.get_documents,
        productId,
        "aiProposal",
        pageSize,
        continuationToken,
    )


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.connection(argName="aiSql", alias="PimAiSql")
@udf.function()
def generate_proposal(
    cosmosDb: fn.FabricItem,
    aiSql: fn.FabricSqlConnection,
    myContext: fn.UserDataFunctionContext,
    payload: dict,
) -> dict:
    return invoke(
        cosmosDb,
        myContext,
        ("read", "write"),
        backend.generate_proposal,
        payload,
        aiSql,
    )


@udf.context(argName="myContext")
@udf.generic_connection(argName="cosmosDb", audienceType="CosmosDB")
@udf.function()
def decide_proposal(
    cosmosDb: fn.FabricItem, myContext: fn.UserDataFunctionContext, payload: dict
) -> dict:
    return invoke(
        cosmosDb, myContext, ("read", "write"), backend.decide_proposal, payload
    )
