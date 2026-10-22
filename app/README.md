# Product catalog app

Rayfin frontend and server-side Functions bridge for the
[Fabric backend](../backend/README.md).

## Configuration

The Functions runtime requires all of these settings; none has a default:

| Setting | Purpose |
| --- | --- |
| `PIM_WORKSPACE_ID` | Existing backend workspace UUID |
| `PIM_UDF_ITEM_ID` | Existing backend UDF item UUID |
| `PIM_RAYFIN_ENDPOINT` | Exact HTTPS Rayfin AppBackend endpoint |
| `PIM_CALLER_TENANT_ID` | Approved signed caller tenant UUID |
| `PIM_CALLER_AUDIENCE` | Exact signed caller-token audience UUID |
| `PIM_CALLER_SUBJECT` | Exact verified app/account subject |

Use approved values from your deployment. Do not guess a subject or treat an
unverified token as proof. See
[configuration.example.json](configuration.example.json) for placeholders.
For a local Functions host, supply environment settings or its ignored
`local.settings.json`.

Frontend local configuration belongs in ignored `.env.local`:
`VITE_RAYFIN_API_URL`, `VITE_RAYFIN_PUBLISHABLE_KEY`, and, where required,
`VITE_FABRIC_WORKSPACE_ID`, `VITE_FABRIC_ITEM_ID`, `VITE_FABRIC_PORTAL_URL`.
Never put an owner token in browser configuration.

## Local development

From this folder:

```powershell
npm ci
npm run prepare:local
npm run typecheck
npm run lint
npm test
npm run build
npm run validate:functions
npm run dev:frontend
```

`prepare:local` uses the installed CLI's version-specific local parser to
generate the typed Functions contract. It does not authenticate or deploy.
Revalidate this wrapper when upgrading Rayfin. Do not hand-edit generated
contracts or use casts to bypass the typed client.

`dev:frontend` starts Vite only. Without approved backend/auth configuration the
authentication gate stays closed. `npm run dev`/`rayfin up` are **not local-only
validation commands** and may change remote resources.

## Hosting and permissions

Publish the backend first. Deploy the app separately through the approved Rayfin
workflow using [rayfin/rayfin.yml](rayfin/rayfin.yml). Authentication and protected
assets must stay enabled. The redirect allowlist currently contains local origins
only; review any hosted redirect explicitly before adding it.

The bridge verifies the signed caller before using the owner's Fabric token.
Downstream UDF operations run as the **app owner**, not as each signed-in user.
This demo is restricted to an explicitly approved account, not a delegated
multi-user authorization design.

## Behavior and limitations

- Browsing reads authoritative catalog pages without depending on search.
- Creation, edits, archive/restore and history use the audited backend.
- Uncertain mutations retain their payload and operation ID in session storage.
  Retry the same operation; do not start a replacement mutation blindly.
- Search is by name or the presets `lightweight-shelter`, `cycling-safety`,
  `trail-riding`. Arbitrary live semantic text is unsupported.
- Search hydration suppresses stale versions/statuses. Missing freshness checks
  mean **not verified**, not current. The app does not schedule reindexing.
- Bridge elapsed time is not Cosmos query latency. DiskANN execution, hosted
  sign-in and live persistence still need acceptance in the target environment.

This folder contains the application runtime and tests, not the original
template's agent skills or scaffolding machinery.
