# cosmos-catalog-translytical - v1.0

Three-product catalog, SQL mirror and audited single-product price write-back.

**Status:** Historical stable baseline; no new live validation performed.


Immutable source commit: `1a496312061d7c7f790e5f88c463163c46a08111`.

## Contents

- [cosmos-catalog-translytical/](cosmos-catalog-translytical/): actual Fabric item definitions,
  notebooks and supporting source, not shortcuts.
- [registration.yml](registration.yml): catalog metadata from the same source.

## Installation and execution

These are browsable source snapshots, not independent Python packages or a new
deployment command. The canonical installer paths in `src` remain unchanged.
Use the repository's Python library and this scenario's logical ID
`cosmos-catalog-translytical`. For a historical version, check out its source commit in a
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
