import { AudienceType, UserDataFunctions, type RayfinContext } from '@microsoft/fabric-user-data-functions';
import { authorizeCaller, RAYFIN_ENDPOINT } from './caller.js';
import { readFailure, readProduct, type ProductReadResult } from './pim.js';
import { mutationFailure, readHistory, updateProduct, type HistoryResult, type MutationInput, type MutationResult } from './pim-actions.js';
import { searchCatalog, searchFailure, type CatalogSearchResult } from './pim-search.js';

const udf = new UserDataFunctions();

udf.func(
  'getConnectionStatus',
  async (ctx: RayfinContext): Promise<{ authorized: boolean; backend: string; writesEnabled: boolean; searchEnabled: boolean }> => ({
    authorized: ctx.baseUrl.replace(/\/+$/, '') === RAYFIN_ENDPOINT.replace(/\/+$/, '')
      && await authorizeCaller(ctx.accessToken, ctx.publishableKey),
    backend: 'PIMv2_ProductPimBackend',
    writesEnabled: true,
    searchEnabled: true,
  }),
  []
);

udf.func(
  'searchCatalog',
  async (queryId: string, status: string, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<CatalogSearchResult> => {
    if (ctx.baseUrl.replace(/\/+$/, '') !== RAYFIN_ENDPOINT.replace(/\/+$/, '')
      || !await authorizeCaller(ctx.accessToken, ctx.publishableKey)) {
      return searchFailure('ACCESS_DENIED', 'This connection is restricted to the approved account.');
    }
    let token: string;
    try { token = ctx.Tokens.Fabric; }
    catch { return searchFailure('OWNER_TOKEN_UNAVAILABLE', 'The app owner connection is unavailable.'); }
    return searchCatalog(queryId, status, token);
  },
  [],
);

udf.func(
  'getProduct',
  async (productId: string, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<ProductReadResult> => {
    if (ctx.baseUrl.replace(/\/+$/, '') !== RAYFIN_ENDPOINT.replace(/\/+$/, '')
      || !await authorizeCaller(ctx.accessToken, ctx.publishableKey)) {
      return readFailure('ACCESS_DENIED', 'This connection is restricted to the approved account.');
    }
    let token: string;
    try {
      token = ctx.Tokens.Fabric;
    } catch {
      return readFailure('OWNER_TOKEN_UNAVAILABLE', 'The app owner connection is unavailable in this runtime.');
    }
    return readProduct(productId, token);
  },
  [],
);

udf.func(
  'getHistory',
  async (productId: string, continuationToken: string, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<HistoryResult> => {
    if (ctx.baseUrl.replace(/\/+$/, '') !== RAYFIN_ENDPOINT.replace(/\/+$/, '')
      || !await authorizeCaller(ctx.accessToken, ctx.publishableKey)) {
      return { ok: false, message: 'Access denied for this account.', items: [], continuationToken: '' };
    }
    try { return await readHistory(productId, continuationToken, ctx.Tokens.Fabric); }
    catch { return { ok: false, message: 'The app owner connection is unavailable.', items: [], continuationToken: '' }; }
  },
  [],
);

udf.func(
  'saveProduct',
  async (payload: MutationInput, ctx: RayfinContext<Record<string, never>, AudienceType.Fabric>): Promise<MutationResult> => {
    if (ctx.baseUrl.replace(/\/+$/, '') !== RAYFIN_ENDPOINT.replace(/\/+$/, '')
      || !await authorizeCaller(ctx.accessToken, ctx.publishableKey)) {
      return mutationFailure('ACCESS_DENIED', 'This connection is restricted to the approved account.');
    }
    let token: string;
    try { token = ctx.Tokens.Fabric; }
    catch { return mutationFailure('OWNER_TOKEN_UNAVAILABLE', 'The app owner connection is unavailable.'); }
    return updateProduct(payload, token);
  },
  [],
);
