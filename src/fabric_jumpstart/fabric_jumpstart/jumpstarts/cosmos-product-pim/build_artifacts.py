"""Build the Fabric UDF payload from the locally tested backend and adapter."""

import argparse
import ast
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).parent
ITEM_NAME = "ProductPimBackend"
PACKAGE = "cosmos_product_pim_backend"
VERSION = "0.3.2"
WHEEL_NAME = f"{PACKAGE}-{VERSION}-py3-none-any.whl"


def backend_wheel() -> bytes:
    dist_info = f"{PACKAGE}-{VERSION}.dist-info"
    files = {
        f"{PACKAGE}.py": (ROOT / "backend.py").read_bytes(),
        f"{dist_info}/METADATA": (
            f"Metadata-Version: 2.1\nName: cosmos-product-pim-backend\n"
            f"Version: {VERSION}\nRequires-Python: >=3.10\n\n"
        ).encode(),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: cosmos-product-pim\n"
            "Root-Is-Purelib: true\nTag: py3-none-any\n"
        ).encode(),
    }
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, content in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest())
        writer.writerow([name, f"sha256={digest.decode().rstrip('=')}", len(content)])
    writer.writerow([f"{dist_info}/RECORD", "", ""])
    files[f"{dist_info}/RECORD"] = record.getvalue().encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 6, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def artifact_files() -> dict[str, bytes]:
    source = (ROOT / "function_app.py").read_text(encoding="utf-8")
    source = source.replace("import backend\n", f"import {PACKAGE} as backend\n")
    functions = []
    metadata = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef) or not node.decorator_list:
            continue
        functions.append(
            {
                "name": node.name,
                "description": f"Product PIM backend: {node.name}.",
                "isPublicEndpointEnabled": True,
            }
        )
        parameters = []
        for argument in node.args.args:
            if argument.arg in {"cosmosDb", "myContext", "aiSql"}:
                continue
            if argument.annotation is None:
                raise ValueError(f"Missing annotation for {node.name}.{argument.arg}")
            parameters.append(
                {"name": argument.arg, "dataType": ast.unparse(argument.annotation)}
            )
        metadata.append(
            {
                "name": node.name,
                "scriptFile": "function_app.py",
                "bindings": [
                    {
                        "name": "req",
                        "type": "HttpTrigger",
                        "direction": "In",
                        "authLevel": "Anonymous",
                        "methods": ["post"],
                        "route": node.name,
                    },
                    {
                        "name": "cosmosDb",
                        "type": "FabricItem",
                        "direction": "In",
                        "itemType": None,
                        "subType": "FabricItem",
                        "alias": None,
                        "audienceType": "CosmosDB",
                    },
                    {
                        "name": "myContext",
                        "type": "UserDataFunctionContext",
                        "direction": "In",
                    },
                ],
                "fabricProperties": {
                    "fabricMetadataSchemaVersion": "1.1.0",
                    "fabricFunctionReturnType": "dict",
                    "fabricFunctionParameters": parameters,
                },
            }
        )
        if any(argument.arg == "aiSql" for argument in node.args.args):
            metadata[-1]["bindings"].append(
                {
                    "name": "aiSql",
                    "type": "FabricItem",
                    "direction": "In",
                    "itemType": None,
                    "subType": "FabricSqlConnection",
                    "alias": "PimAiSql",
                }
            )
    documents = {
        ".platform": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "UserDataFunction", "displayName": ITEM_NAME},
            "config": {
                "version": "2.0",
                "logicalId": "736a032f-7cb6-4434-886c-63f13739b309",
            },
        },
        "definition.json": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/userDataFunction/definition/1.1.0/schema.json",
            "runtime": "PYTHON",
            "connectedDataSources": [],
            "functions": functions,
            "libraries": {
                "public": [
                    {
                        "name": "fabric-user-data-functions",
                        "type": "PYPI",
                        "version": "1.0",
                    },
                    {"name": "azure-cosmos", "type": "PYPI", "version": "4.16.4"},
                ],
                "private": [{"name": WHEEL_NAME, "type": "WHEEL"}],
            },
        },
        ".resources/functions.json": {
            "runtime": "PYTHON",
            "functionsMetadata": metadata,
        },
    }
    files = {
        name: (json.dumps(value, indent=2) + "\n").encode()
        for name, value in documents.items()
    }
    files["function_app.py"] = source.encode()
    files[f"privateLibraries/{WHEEL_NAME}"] = backend_wheel()
    return files


def build(destination: Path, *, check: bool = False) -> None:
    private_libraries = destination / "privateLibraries"
    stale_wheels = (
        [
            path
            for path in private_libraries.glob(f"{PACKAGE}-*.whl")
            if path.name != WHEEL_NAME
        ]
        if private_libraries.is_dir()
        else []
    )
    if check and stale_wheels:
        raise ValueError(f"Stale backend wheel remains: {stale_wheels[0]}")
    if not check:
        for path in stale_wheels:
            path.unlink()
    for name, content in artifact_files().items():
        path = destination / name
        if check:
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError(f"Artifact is missing or stale: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    build(ROOT / f"{ITEM_NAME}.UserDataFunction", check=arguments.check)
