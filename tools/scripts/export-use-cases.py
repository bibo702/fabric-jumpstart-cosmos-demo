"""Export browsable scenario snapshots without moving the installer's sources."""

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "use-cases"
SCENARIOS = "src/fabric_jumpstart/fabric_jumpstart/jumpstarts"
APP = "src/cosmos_product_pim_rayfin"


@dataclass(frozen=True)
class Snapshot:
    scenario: str
    version: str
    ref: str | None
    purpose: str
    status: str
    app: bool = False


SNAPSHOTS = (
    Snapshot(
        "hello-world",
        "current",
        None,
        "Minimal notebook installation smoke test.",
        "Local tutorial; live deployment is not verified by this export.",
    ),
    Snapshot(
        "cosmos-db-data-pipeline",
        "current",
        None,
        "Cosmos DB -> Bronze -> Silver -> Gold -> Cosmos DB.",
        "Local tutorial; connected execution requires operator configuration.",
    ),
    Snapshot(
        "cosmos-catalog-translytical",
        "v1.0",
        "1a496312061d7c7f790e5f88c463163c46a08111",
        "Three-product catalog, SQL mirror and audited single-product price write-back.",
        "Historical stable baseline; no new live validation performed.",
    ),
    Snapshot(
        "cosmos-catalog-translytical",
        "v1.1",
        "95c6cf12adb2aaf9064ec103d3ad96fad393e7ea",
        "120 products, six categories, bulk price changes and price-audit history.",
        "Historical stable baseline; no new live validation performed.",
    ),
    Snapshot(
        "cosmos-product-pim",
        "v2.0-checkpoint",
        "385160767294fe6dac06bab810193242c8fa095f",
        "Product-partitioned backend, conditional edits, retry receipts and audit events.",
        "Pre-Rayfin WIP checkpoint, not a release. Source and generated UDF artifacts "
        "differ; do not deploy blindly. The deferred v2.1 AI probe is experimental.",
    ),
    Snapshot(
        "cosmos-product-pim",
        "v0.3.0",
        "ae1dea9d9da08cf81f10ee95f6f1e17f62b4dd68",
        "Native Cosmos vector/BM25/RRF search and Fabric-generated embeddings.",
        "Historical tagged source; Rayfin search integration was still gated.",
        True,
    ),
    Snapshot(
        "cosmos-product-pim",
        "v0.3.1",
        "d9203851369119f05adf7c71bcc0662b43bd0a29",
        "Stored semantic-query presets and the authenticated Rayfin search bridge.",
        "Historical tagged source; not a claim of current hosted readiness.",
        True,
    ),
    Snapshot(
        "cosmos-product-pim",
        "v0.3.2",
        "a01ffbc5534f4677fd9e4576354533f2ce87d4ee",
        "Free-text product-name search alongside preset-based semantic search.",
        "Historical tagged source; not a claim of current hosted readiness.",
        True,
    ),
    Snapshot(
        "cosmos-product-pim",
        "v0.4.0-unreleased",
        None,
        "Catalog creation/browsing, 1,200-product search demo and incremental reindexing.",
        "Unreleased local implementation. Hosted authentication, scheduled indexing, "
        "relevance and actual DiskANN execution still require live acceptance.",
        True,
    ),
)


def git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True
    ).stdout


def exportable(name: str) -> bool:
    path = PurePosixPath(name)
    excluded = {
        ".agents",
        ".vscode",
        ".git",
        "node_modules",
        "__pycache__",
        "dist",
        "coverage",
        ".venv",
        ".vite",
        ".next",
    }
    return (
        not excluded.intersection(path.parts)
        and path.name
        not in {
            "AGENTS.md",
            ".mcp.json",
            ".lockfile.json",
            "local.settings.json",
            "deploymentdata.json",
            ".deployments.json",
            "fabric.generated.ts",
        }
        and not path.name.startswith(".env")
        and not path.name.endswith((".pyc", ".pyo", ".tsbuildinfo", ".log"))
    )


def source_files(snapshot: Snapshot) -> dict[str, bytes]:
    paths = [
        f"{SCENARIOS}/{snapshot.scenario}",
        f"{SCENARIOS}/community/{snapshot.scenario}.yml",
    ]
    if snapshot.app:
        paths.append(APP)
    if snapshot.ref:
        archive = git("archive", snapshot.ref, *paths)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
            files = {}
            for member in tree.getmembers():
                if member.isfile() and exportable(member.name):
                    stream = tree.extractfile(member)
                    if stream is None:
                        raise ValueError(f"Cannot read archived file: {member.name}")
                    files[member.name] = stream.read()
            return files
    names = (
        git(
            "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *paths
        )
        .decode()
        .split("\0")
    )
    return {
        name: (ROOT / name).read_bytes()
        for name in sorted(set(names))
        if name and exportable(name) and (ROOT / name).is_file()
    }


def frozen_files(snapshot: Snapshot) -> dict[str, bytes]:
    folder = OUTPUT / snapshot.scenario / snapshot.version
    inventory = folder / "snapshot-files.json"
    if not inventory.is_file():
        raise ValueError(f"Missing {inventory}; export with --refresh-current first.")
    files = {"snapshot-files.json": inventory.read_bytes()}
    for name, digest in json.loads(files["snapshot-files.json"])["files"].items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError(f"Invalid snapshot path: {name}")
        data = (folder / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Snapshot checksum mismatch: {folder / name}")
        files[name] = data
    return files


def snapshot_files(
    snapshot: Snapshot, refresh_current: bool = False
) -> dict[str, bytes]:
    if not refresh_current:
        return frozen_files(snapshot)
    files = {}
    source_root = f"{SCENARIOS}/{snapshot.scenario}/"
    for name, content in source_files(snapshot).items():
        if name.startswith(source_root):
            relative = f"{snapshot.scenario}/{name.removeprefix(source_root)}"
        elif name.startswith(f"{APP}/"):
            relative = f"app/{name.removeprefix(APP + '/')}"
        else:
            relative = "registration.yml"
        files[relative] = content
    if not any(name.endswith("/.platform") for name in files):
        raise ValueError(f"No Fabric items found for {snapshot}")
    provenance = (
        f"Immutable source commit: `{snapshot.ref}`."
        if snapshot.ref
        else "Source: working files at export time, including local additions. "
        "This is not a tagged release. The checksum inventory preserves this snapshot "
        "independently of later edits to the canonical sources."
    )
    app_note = (
        "\n- [Rayfin application](app/): matching frontend, Functions bridge, manifests "
        "and application tests. Developer agent skills and local environment/deployment "
        "state are intentionally excluded. Template-scaffolding commands are not part "
        "of this runtime export. Use the canonical app for template development.\n"
        if snapshot.app
        else ""
    )
    artifact_note = (
        "\nHistorical packaging note: the original 0.3.x UDF text/JSON artifacts "
        "have formatting/line-ending differences from their builder output. "
        "The original bytes are preserved here; a strict `build_artifacts.py --check` "
        "reports these differences. Parsed JSON, normalized Python source and wheel "
        "bytes were checked separately. This is not a newly rebuilt release.\n"
        if snapshot.ref and snapshot.app
        else ""
    )
    text = f"""# {snapshot.scenario} - {snapshot.version}

{snapshot.purpose}

**Status:** {snapshot.status}
{artifact_note}

{provenance}

## Contents

- [{snapshot.scenario}/]({snapshot.scenario}/): actual Fabric item definitions,
  notebooks and supporting source, not shortcuts.
- [registration.yml](registration.yml): catalog metadata from the same source.
{app_note}
## Installation and execution

These are browsable source snapshots, not independent Python packages or a new
deployment command. The canonical installer paths in `src` remain unchanged.
Use the repository's Python library and this scenario's logical ID
`{snapshot.scenario}`. For a historical version, check out its source commit in a
separate clone and install that checkout's library, rather than assuming the latest
PyPI package or current checkout installs this snapshot.

The registration's `source` block is preserved as historical metadata; it is not
rewritten to point at this folder. Do not register this copied YAML unchanged as a
new local scenario. Cosmos database provisioning, UDF publication, grants and app
deployment have prerequisites beyond copying Fabric item definitions.

Start with the entry-point notebook named in the registration. Setup and run
instructions inside the copied source describe that version's behavior.
Historical README paths and commands are preserved verbatim and refer to their
original checkout layout. For versions with an app, its source is now in `app/`.
Use isolated workspace/item names when comparing versions. Exporting these folders
does not create resources, run notebooks, enable schedules or change an existing
deployment.
"""
    files["README.md"] = text.encode()
    inventory = {
        "base_commit": snapshot.ref or git("rev-parse", "HEAD").decode().strip(),
        "source": "git" if snapshot.ref else "working-tree",
        "files": {
            name: hashlib.sha256(data).hexdigest()
            for name, data in sorted(files.items())
        },
    }
    files["snapshot-files.json"] = (json.dumps(inventory, indent=2) + "\n").encode()
    return files


def expected_files(refresh_current: bool = False) -> dict[Path, bytes]:
    result = {}
    for snapshot in SNAPSHOTS:
        prefix = Path(snapshot.scenario) / snapshot.version
        result.update(
            {
                prefix / name: data
                for name, data in snapshot_files(snapshot, refresh_current).items()
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Check without writing files."
    )
    parser.add_argument(
        "--refresh-current",
        action="store_true",
        help="Rebuild from pinned Git history and replace working-source snapshots.",
    )
    args = parser.parse_args()
    expected = expected_files(args.refresh_current)
    # Top-level and use-case overview pages are authored, not exported.
    managed = {
        path.relative_to(OUTPUT)
        for path in OUTPUT.rglob("*")
        if path.is_file()
        and path != OUTPUT / ".gitattributes"
        and not (path.name == "README.md" and len(path.relative_to(OUTPUT).parts) <= 2)
    }
    extras = managed - expected.keys()
    if extras:
        raise SystemExit(
            "Unexpected export files (remove explicitly if obsolete): "
            + ", ".join(str(path) for path in sorted(extras))
        )
    changed = [
        path
        for path, data in expected.items()
        if not (OUTPUT / path).is_file() or (OUTPUT / path).read_bytes() != data
    ]
    if args.check:
        if changed:
            raise SystemExit(
                "Out-of-date exports: " + ", ".join(str(path) for path in changed)
            )
        print(f"Verified {len(SNAPSHOTS)} snapshots, {len(expected)} files.")
        return
    for path in changed:
        target = OUTPUT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(expected[path])
    print(
        f"Exported {len(SNAPSHOTS)} snapshots, {len(expected)} files "
        f"({len(changed)} written)."
    )


if __name__ == "__main__":
    main()
