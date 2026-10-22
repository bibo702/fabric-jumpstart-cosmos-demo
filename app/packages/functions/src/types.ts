/**
 * Function schema types for RayfinClient.
 *
 * AUTO-GENERATED — do not edit manually.
 * Re-generated automatically when function source files change.
 *
 * If this file is not updating automatically, run:
 *   rayfin dev functions apply
 *
 * The schema is a closed object type: only the function names listed
 * below are accepted by RayfinClient.functions.<name>.invoke(...).
 * Adding, renaming, or changing the signature of a udf.func() call
 * regenerates this file and surfaces type errors at every consumer.
 *
 * IMPORTANT: This file must NOT import any Node.js packages — it is
 * resolved by the frontend app's TypeScript compiler.
 */

export type AppFunctionsSchema = {
  getConnectionStatus: {
    input: Record<string, never>;
    output: { authorized: boolean; backend: string; writesEnabled: boolean; searchEnabled: boolean; readProbe: 'not-run' | 'passed' | 'failed'; searchProbe: 'not-run' | 'passed' | 'failed' | 'pending'; writes: 'not-configured' | 'configured-not-verified' };
  };
  listProducts: {
    input: { pageSize: number; afterProductId: string };
    output: { ok: boolean; message: string; items: { productId: string; name: string; description: string; categoryName: string; status: string; version: number }[]; afterProductId: string };
  };
  getSearchIndexStatus: {
    input: { productIds: string[] };
    output: { ok: boolean; message: string; items: { productId: string; sourceVersion: null | number; version: number; status: 'pending' | 'current' }[]; pendingCount: number };
  };
  createProduct: {
    input: { payload: { productId: string; operationId: string; reason: string; name: string; description: string; categoryName: string } };
    output: { ok: boolean; outcome: 'applied' | 'rejected' | 'unknown'; code: string; message: string; version: number; replayed: boolean; indexingPending: boolean };
  };
  searchCatalog: {
    input: { queryId: string; status: string };
    output: { diagnostics: { requestCharge: null | number; queryMetrics: string[]; indexMetrics: string[]; scope: 'search-query-only' }; staleCount: number; indexingPending: boolean; ok: boolean; code: string; message: string; queryId: string; label: string; queryText: string; queryTerms: string[]; embeddingDimensions: number; ranking: string; elapsedMs: number; items: { rank: number; sourceVersion: number; productId: string; name: string; description: string; categoryName: string; status: string; version: number }[] };
  };
  searchCatalogByName: {
    input: { queryText: string; status: string };
    output: { diagnostics: { requestCharge: null | number; queryMetrics: string[]; indexMetrics: string[]; scope: 'search-query-only' }; staleCount: number; indexingPending: boolean; ok: boolean; code: string; message: string; queryText: string; queryTerms: string[]; ranking: string; elapsedMs: number; items: { rank: number; sourceVersion: number; productId: string; name: string; description: string; categoryName: string; status: string; version: number }[] };
  };
  getProduct: {
    input: { productId: string };
    output: { ok: boolean; code: string; message: string; product: null | { productId: string; name: string; description: string; categoryName: string; status: string; version: number } };
  };
  getHistory: {
    input: { productId: string; continuationToken: string };
    output: { ok: boolean; message: string; items: { id: string; action: string; occurredAt: string; fromVersion: number; toVersion: number; actor: { oid: string; tenantId: string; username: string }; reason: string; operationId: string; changes: { path: string; oldValue: null | string; newValue: null | string }[] }[]; continuationToken: string };
  };
  saveProduct: {
    input: { payload: { productId: string; expectedVersion: number; operationId: string; reason: string; changes: { name?: undefined | string; description?: undefined | string; categoryName?: undefined | string; status?: undefined | string } } };
    output: { ok: boolean; outcome: 'applied' | 'rejected' | 'unknown'; code: string; message: string; version: number; replayed: boolean; indexingPending: boolean };
  };
};
