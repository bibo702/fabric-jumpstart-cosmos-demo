"""Explicit, isolated Fabric SQL AI connection probe; never changes product data."""

import argparse
import base64
import importlib.util
import json
from pathlib import Path
import time

import requests

from fabric_jumpstart.utils import _decode_jwt, resolve_token_credential


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "status", "invoke"])
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--sql-endpoint")
    parser.add_argument("--item")
    parser.add_argument("--operation")
    args = parser.parse_args()
    credential = resolve_token_credential()
    token = credential.get_token("https://api.fabric.microsoft.com/.default").token
    claims = _decode_jwt(token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"https://api.fabric.microsoft.com/v1/workspaces/{args.workspace}"
    started = time.perf_counter()
    if args.action == "status":
        if not args.operation:
            parser.error("--operation is required")
        response = requests.get(
            f"https://api.fabric.microsoft.com/v1/operations/{args.operation}",
            headers=headers,
            timeout=30,
        )
    elif args.action == "invoke":
        if not args.item:
            parser.error("--item is required")
        response = requests.post(
            f"{base}/userDataFunctions/{args.item}/functions/probe_ai/invoke",
            headers=headers,
            json={},
            timeout=100,
        )
    else:
        if not args.sql_endpoint:
            parser.error("--sql-endpoint is required")
        if not claims.get("scp") or not claims.get("oid") or not claims.get("tid"):
            raise ValueError("A delegated user identity is required")
        endpoint = requests.get(
            f"{base}/sqlEndpoints/{args.sql_endpoint}", headers=headers, timeout=30
        )
        endpoint.raise_for_status()
        spec = importlib.util.spec_from_file_location(
            "pim_builder", Path(__file__).with_name("build_artifacts.py")
        )
        assert spec and spec.loader
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        source = f"""import fabric.functions as fn
import cosmos_product_pim_backend as backend
udf = fn.UserDataFunctions()
PRINCIPAL_GRANTS = {repr({claims["tid"] + ":" + claims["oid"]: ["read"]})}

@udf.context(argName="myContext")
@udf.connection(argName="aiSql", alias="PimAiSql")
@udf.function()
def probe_ai(aiSql: fn.FabricSqlConnection, myContext: fn.UserDataFunctionContext) -> dict:
    try:
        backend.authorize(backend.caller_identity(myContext), PRINCIPAL_GRANTS, "read")
        return backend.generate_description(aiSql, {{"product": {{"name": "Trail bike", "description": "Aluminum frame with 21 gears."}}, "reviews": []}})
    except backend.BackendError as error:
        return {{"status": "rejected", "code": error.code, "message": str(error)}}
"""
        definition = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/userDataFunction/definition/1.1.0/schema.json",
            "runtime": "PYTHON",
            "connectedDataSources": [
                {
                    "alias": "PimAiSql",
                    "artifactId": args.sql_endpoint,
                    "artifactType": endpoint.json()["type"],
                    "workspaceId": args.workspace,
                }
            ],
            "functions": [
                {
                    "name": "probe_ai",
                    "description": "Synthetic SQL AI compatibility probe",
                    "isPublicEndpointEnabled": True,
                }
            ],
            "libraries": {
                "public": [
                    {
                        "name": "fabric-user-data-functions",
                        "type": "PYPI",
                        "version": "1.0",
                    }
                ],
                "private": [{"name": builder.WHEEL_NAME, "type": "WHEEL"}],
            },
        }
        metadata = {
            "runtime": "PYTHON",
            "functionsMetadata": [
                {
                    "name": "probe_ai",
                    "scriptFile": "function_app.py",
                    "bindings": [
                        {
                            "name": "req",
                            "type": "HttpTrigger",
                            "direction": "In",
                            "authLevel": "Anonymous",
                            "methods": ["post"],
                            "route": "probe_ai",
                        },
                        {
                            "name": "myContext",
                            "type": "UserDataFunctionContext",
                            "direction": "In",
                        },
                        {
                            "name": "aiSql",
                            "type": "FabricItem",
                            "direction": "In",
                            "itemType": None,
                            "subType": "FabricSqlConnection",
                            "alias": "PimAiSql",
                        },
                    ],
                    "fabricProperties": {
                        "fabricMetadataSchemaVersion": "1.1.0",
                        "fabricFunctionReturnType": "dict",
                        "fabricFunctionParameters": [],
                    },
                }
            ],
        }
        files = {
            "function_app.py": source.encode(),
            "definition.json": json.dumps(definition).encode(),
            ".resources/functions.json": json.dumps(metadata).encode(),
            f"privateLibraries/{builder.WHEEL_NAME}": builder.backend_wheel(),
        }
        parts = [
            {
                "path": name,
                "payload": base64.b64encode(content).decode(),
                "payloadType": "InlineBase64",
            }
            for name, content in files.items()
        ]
        response = requests.post(
            f"{base}/userDataFunctions",
            headers=headers,
            json={
                "displayName": "PIMv2_AiConnectionProbe",
                "description": "Isolated synthetic AI probe; no Cosmos data writes.",
                "definition": {"parts": parts},
            },
            timeout=100,
        )
    print(
        json.dumps(
            {
                "httpStatus": response.status_code,
                "elapsedMs": round((time.perf_counter() - started) * 1000),
                "operationId": response.headers.get("x-ms-operation-id"),
                "location": response.headers.get("Location"),
                "body": response.text,
            },
            indent=2,
        )
    )
    response.raise_for_status()


if __name__ == "__main__":
    main()
