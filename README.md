# Cosmos Product Catalog

A product catalog demo using **Cosmos DB in Microsoft Fabric**, **Fabric User
Data Functions**, and a **Rayfin web app**.

## What it does

- Browse, create, edit, archive and restore products.
- Keep audited, retry-safe product changes.
- Search by product name or three predefined semantic-search examples.
- Refresh the derived search index with a Fabric notebook.

## Repository

| Folder | Contents |
| --- | --- |
| [backend/](backend/) | Cosmos container definitions, Python backend, deployable UDF and three Fabric notebooks |
| [app/](app/) | Rayfin frontend and authenticated Functions bridge |
| [tests/](tests/) | Backend and notebook-contract tests |

There is one current implementation. No Fabric Jumpstart website/library,
unrelated demos, duplicated versions or snapshot-export tooling is included.
Older commits and branches remain available in Git history.

## Start here

1. Follow [backend setup](backend/README.md) to configure the Cosmos database,
   backend grants and Fabric items.
2. Run `00_ProductPimSetup`, then `01_ProductPimHybridSearch`.
3. Follow [app setup](app/README.md) with your approved backend/app configuration.
4. Enable a schedule for `02_ProductPimReindex` only after validating it manually.

This repository contains source and Fabric item definitions, **not a standalone
one-command installer**. Creating or changing live resources is an explicit
operator step.

## Local checks

Backend checks require Python 3.10-3.13 and pytest
([requirements-dev.txt](requirements-dev.txt)):

```powershell
python backend\build_artifacts.py --check
python -m pytest tests
```

For the app, use its existing npm workspace:

```powershell
Set-Location app
npm ci
npm run prepare:local
npm run typecheck
npm run lint
npm test
npm run build
```

The current implementation is unreleased. Local tests do not prove hosted
authentication, scheduled execution, search relevance or actual DiskANN index
usage. Semantic search uses named pre-embedded examples, not arbitrary live
semantic text. There is no shopping-cart/checkout feature.
