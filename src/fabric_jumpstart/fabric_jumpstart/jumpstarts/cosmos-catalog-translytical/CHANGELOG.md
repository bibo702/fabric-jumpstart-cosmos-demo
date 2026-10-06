# Cosmos Catalog Translytical Version History

## v1.1 (current working version)

Built on the stable v1.0 UDF contract without adding another function.

- Replaced the three-row seed with 120 deterministic products across Bikes, Accessories, Camping, Clothing, Components, and Nutrition.
- Preserved `helmet-200` at version 1 so the original acceptance test remains repeatable on a fresh deployment.
- Added deterministic historical `priceChange` documents for immediate analytics and audit demonstrations.
- Kept setup reruns non-destructive: existing products and audit records are never overwritten.
- Added category filtering, selection of up to 25 products, and bounded percentage-based bulk price changes.
- Added a recent audit-history view sourced directly from Cosmos DB.
- Continued routing every mutation through the existing `PriceWriteback.update_prices` User Data Function.

Power BI remains deferred to the final increment, after the operational write-back workflow and mirrored schema are stable.

## v1.0 (stable)

Git commit: `1a496312061d7c7f790e5f88c463163c46a08111`

- Provisioned the Cosmos DB database and `/categoryName`-partitioned `SampleData` container.
- Seeded three representative products, including the `helmet-200` acceptance product.
- Added the guided single-product write-back notebook.
- Added the reusable `PriceWriteback.update_prices` User Data Function with validation, optimistic concurrency, transactional audit creation, and a 25-update bulk contract.
- Fixed Fabric publication metadata placement and runtime annotation handling.
- Verified setup, write-back, conflict, and audit behavior in Fabric.
