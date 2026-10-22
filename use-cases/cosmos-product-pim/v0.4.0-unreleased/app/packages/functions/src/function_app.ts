import { AudienceType, UserDataFunctions, type RayfinContext } from '@microsoft/fabric-user-data-functions';
import { authorizeCaller } from './caller.js';
import { configured, validEndpoint } from './config.js';
import { readFailure, readProduct, type ProductReadResult } from './pim.js';
import { createProduct, mutationFailure, readHistory, updateProduct, type CreateInput, type HistoryResult, type MutationInput, type MutationResult } from './pim-actions.js';
import { getSearchIndexStatus, listProducts, type CatalogPage, type IndexStatus } from './pim-catalog.js';
import { probeBackend } from './pim-health.js';
import { searchCatalog, searchCatalogByName, searchFailure, type CatalogSearchResult, type NameSearchResult } from './pim-search.js';

const udf = new UserDataFunctions();

async function authorized(ctx: RayfinContext): Promise<boolean> {
  return validEndpoint(ctx.baseUrl) && await authorizeCaller(ctx.accessToken, ctx.publishableKey);
}

export interface ConnectionStatus {
  authorized: boolean;
  backend: string;
  writesEnabled: boolean;
  searchEnabled: boolean;
  readProbe: 'not-run' | 'passed' | 'failed';
  searchProbe: 'not-run' | 'passed' | 'pending' | 'failed';
  writes: 'not-configured' | 'configured-not-verified';
}

udf.func('getConnectionStatus', async (ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<ConnectionStatus> => {
  const result: ConnectionStatus = { authorized: false, backend: 'Configured PIM UDF', writesEnabled: false,
    searchEnabled: false, readProbe: 'not-run', searchProbe: 'not-run', writes: 'not-configured' };
  if (!await authorized(ctx)) return result;
  result.authorized = true;
  result.writesEnabled = configured();
  result.writes = result.writesEnabled ? 'configured-not-verified' : 'not-configured';
  try {
    const token = ctx.Tokens.Fabric;
    Object.assign(result, await probeBackend(token));
  } catch {
    result.readProbe = 'failed';
    result.searchProbe = 'failed';
  }
  return result;
}, []);

udf.func('listProducts', async (pageSize: number, afterProductId: string, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<CatalogPage> => {
  if (!await authorized(ctx)) return { ok: false, message: 'Access denied or configuration missing.', items: [], afterProductId: '' };
  try { return await listProducts(pageSize, afterProductId, ctx.Tokens.Fabric); }
  catch { return { ok: false, message: 'The app owner connection is unavailable.', items: [], afterProductId: '' }; }
}, []);

udf.func('getSearchIndexStatus', async (productIds: string[], ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<IndexStatus> => {
  if (!await authorized(ctx)) return { ok: false, message: 'Access denied or configuration missing.', items: [], pendingCount: 0 };
  try { return await getSearchIndexStatus(productIds, ctx.Tokens.Fabric); }
  catch { return { ok: false, message: 'The app owner connection is unavailable.', items: [], pendingCount: 0 }; }
}, []);

udf.func('createProduct', async (payload: CreateInput, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<MutationResult> => {
  if (!await authorized(ctx)) return mutationFailure('ACCESS_DENIED', 'Access denied or configuration missing.');
  try { return await createProduct(payload, ctx.Tokens.Fabric); }
  catch { return mutationFailure('OWNER_TOKEN_UNAVAILABLE', 'The app owner connection is unavailable.'); }
}, []);

udf.func('searchCatalog', async (queryId: string, status: string, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<CatalogSearchResult> => {
  if (!await authorized(ctx)) return searchFailure('ACCESS_DENIED', 'Access denied or configuration missing.');
  try { return await searchCatalog(queryId, status, ctx.Tokens.Fabric); }
  catch { return searchFailure('OWNER_TOKEN_UNAVAILABLE', 'The app owner connection is unavailable.'); }
}, []);

udf.func('searchCatalogByName', async (queryText: string, status: string, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<NameSearchResult> => {
  if (!await authorized(ctx)) return searchFailure('ACCESS_DENIED', 'Access denied or configuration missing.');
  try { return await searchCatalogByName(queryText, status, ctx.Tokens.Fabric); }
  catch { return searchFailure('OWNER_TOKEN_UNAVAILABLE', 'The app owner connection is unavailable.'); }
}, []);

udf.func('getProduct', async (productId: string, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<ProductReadResult> => {
  if (!await authorized(ctx)) return readFailure('ACCESS_DENIED', 'Access denied or configuration missing.');
  try { return await readProduct(productId, ctx.Tokens.Fabric); }
  catch { return readFailure('OWNER_TOKEN_UNAVAILABLE', 'The app owner connection is unavailable.'); }
}, []);

udf.func('getHistory', async (productId: string, continuationToken: string, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<HistoryResult> => {
  if (!await authorized(ctx)) return { ok: false, message: 'Access denied or configuration missing.', items: [], continuationToken: '' };
  try { return await readHistory(productId, continuationToken, ctx.Tokens.Fabric); }
  catch { return { ok: false, message: 'The app owner connection is unavailable.', items: [], continuationToken: '' }; }
}, []);

udf.func('saveProduct', async (payload: MutationInput, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<MutationResult> => {
  if (!await authorized(ctx)) return mutationFailure('ACCESS_DENIED', 'Access denied or configuration missing.');
  try { return await updateProduct(payload, ctx.Tokens.Fabric); }
  catch { return mutationFailure('OWNER_TOKEN_UNAVAILABLE', 'The app owner connection is unavailable.'); }
}, []);
