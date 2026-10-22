# cosmos-product-pim - v0.4.0-unreleased

Catalog creation/browsing, 1,200-product search demo and incremental reindexing.

**Status:** Unreleased local implementation. Hosted authentication, scheduled indexing, relevance and actual DiskANN execution still require live acceptance.


Source: working files at export time, including local additions. This is not a tagged release. The checksum inventory preserves this snapshot independently of later edits to the canonical sources.

## Contents

- [cosmos-product-pim/](cosmos-product-pim/): actual Fabric item definitions,
  notebooks and supporting source, not shortcuts.
- [registration.yml](registration.yml): catalog metadata from the same source.

- [Rayfin application](app/): matching frontend, Functions bridge, manifests and application tests. Developer agent skills and local environment/deployment state are intentionally excluded. Template-scaffolding commands are not part of this runtime export. Use the canonical app for template development.

## Installation and execution

These are browsable source snapshots, not independent Python packages or a new
deployment command. The canonical installer paths in `src` remain unchanged.
Use the repository's Python library and this scenario's logical ID
`cosmos-product-pim`. For a historical version, check out its source commit in a
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
