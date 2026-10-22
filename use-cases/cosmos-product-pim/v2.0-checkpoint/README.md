# cosmos-product-pim - v2.0-checkpoint

Product-partitioned backend, conditional edits, retry receipts and audit events.

**Status:** Pre-Rayfin WIP checkpoint, not a release. Source and generated UDF artifacts differ; do not deploy blindly. The deferred v2.1 AI probe is experimental.


Immutable source commit: `385160767294fe6dac06bab810193242c8fa095f`.

## Contents

- [cosmos-product-pim/](cosmos-product-pim/): actual Fabric item definitions,
  notebooks and supporting source, not shortcuts.
- [registration.yml](registration.yml): catalog metadata from the same source.

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
