import {
  udfUrl,
  isRecord,
  readBody,
  readProduct,
  type ProductSummary,
} from './pim.js';

export type SearchStatus = 'all' | 'active' | 'deleted';
export interface SearchDiagnostics {
  requestCharge: number | null;
  queryMetrics: string[];
  indexMetrics: string[];
  scope: 'search-query-only';
}

export interface SearchResultItem extends ProductSummary {
  rank: number;
  sourceVersion: number;
}

export interface CatalogSearchResult {
  diagnostics: SearchDiagnostics;
  staleCount: number;
  indexingPending: boolean;
  ok: boolean;
  code: string;
  message: string;
  queryId: string;
  label: string;
  queryText: string;
  queryTerms: string[];
  embeddingDimensions: number;
  ranking: string;
  elapsedMs: number;
  items: SearchResultItem[];
}

export interface NameSearchResult {
  diagnostics: SearchDiagnostics;
  staleCount: number;
  indexingPending: boolean;
  ok: boolean;
  code: string;
  message: string;
  queryText: string;
  queryTerms: string[];
  ranking: string;
  elapsedMs: number;
  items: SearchResultItem[];
}

const QUERY_IDS = new Set([
  'lightweight-shelter',
  'cycling-safety',
  'trail-riding',
]);

export function searchFailure(code: string, message: string): CatalogSearchResult {
  return {
    diagnostics: diagnostics(),
    staleCount: 0, indexingPending: false,
    ok: false,
    code,
    message,
    queryId: '',
    label: '',
    queryText: '',
    queryTerms: [],
    embeddingDimensions: 0,
    ranking: '',
    elapsedMs: 0,
    items: [],
  };
}

function diagnostics(output?: Record<string, unknown>): SearchDiagnostics {
  const value = output?.diagnostics;
  const empty: SearchDiagnostics = { requestCharge: null, queryMetrics: [], indexMetrics: [], scope: 'search-query-only' };
  if (!isRecord(value) || value.scope !== 'search-query-only') return empty;
  const metrics = (input: unknown): string[] => Array.isArray(input) && input.length <= 50
    && input.every((item) => typeof item === 'string' && item.length <= 10_000) ? input : [];
  return { ...empty, requestCharge: typeof value.requestCharge === 'number' && Number.isFinite(value.requestCharge) && value.requestCharge >= 0 ? value.requestCharge : null,
    queryMetrics: metrics(value.queryMetrics), indexMetrics: metrics(value.indexMetrics) };
}
function freshness(output: Record<string, unknown>) {
  if (typeof output.staleCount !== 'number' || !Number.isSafeInteger(output.staleCount) || output.staleCount < 0
    || typeof output.indexingPending !== 'boolean') throw new Error('Missing freshness metadata');
  return { staleCount: output.staleCount, indexingPending: output.indexingPending };
}

async function hydrate(rankedItems: { productId: string; sourceVersion: number; status: string }[], status: SearchStatus, token: string, request: typeof fetch) {
  if (rankedItems.length > 10 || new Set(rankedItems.map((item) => item.productId)).size !== rankedItems.length) throw new Error('Invalid ranks');
  const products = await Promise.all(rankedItems.map((item) => readProduct(item.productId, token, request)));
  const items: SearchResultItem[] = [];
  let staleCount = 0;
  products.forEach((result, index) => {
    const ranked = rankedItems[index];
    const product = result.product;
    if (!result.ok && result.code !== 'NOT_FOUND') throw new Error('Authoritative read failed');
    if (!product || product.version !== ranked.sourceVersion || product.status !== ranked.status
      || (status !== 'all' && product.status !== status)) { staleCount++; return; }
    items.push({ ...product, rank: index + 1, sourceVersion: ranked.sourceVersion });
  });
  return { items, staleCount };
}

function validStatus(value: string): value is SearchStatus {
  return value === 'all' || value === 'active' || value === 'deleted';
}

function validNameQuery(value: string): boolean {
  return typeof value === 'string'
    && value.trim().length >= 2
    && value.trim().length <= 100;
}

function validRankedItem(
  value: unknown,
): value is { productId: string; sourceVersion: number; status: string } {
  return isRecord(value)
    && typeof value.productId === 'string'
    && /^[a-zA-Z0-9_-]{1,100}$/.test(value.productId)
    && typeof value.sourceVersion === 'number'
    && Number.isSafeInteger(value.sourceVersion)
    && value.sourceVersion > 0
    && (value.status === 'active' || value.status === 'deleted');
}

export async function searchCatalog(
  queryId: string,
  status: string,
  ownerToken: string,
  request: typeof fetch = fetch,
): Promise<CatalogSearchResult> {
  if (!QUERY_IDS.has(queryId) || !validStatus(status)) {
    return searchFailure('INVALID_SEARCH', 'Choose one of the available demo searches.');
  }
  if (!ownerToken) {
    return searchFailure('OWNER_TOKEN_UNAVAILABLE', 'The app owner connection is unavailable.');
  }
  const startedAt = Date.now();
  try {
    const response = await request(udfUrl('search_products_by_query'), {
      method: 'POST',
      headers: {
        Authorization: ['Bearer', ownerToken].join(' '),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ queryId, pageSize: 10, status }),
      signal: AbortSignal.timeout(25_000),
      redirect: 'error',
    });
    if (!response.ok) {
      await response.body?.cancel();
      return searchFailure('SEARCH_UNAVAILABLE', 'Hybrid search is unavailable. Check the published PIM backend and retry.');
    }
    const envelope = await readBody(response);
    if (!isRecord(envelope) || envelope.status !== 'Succeeded'
      || envelope.functionName !== 'search_products_by_query'
      || !Array.isArray(envelope.errors) || envelope.errors.length !== 0
      || !isRecord(envelope.output)) {
      return searchFailure('INVALID_RESPONSE', 'The PIM backend returned an unexpected search response.');
    }
    const output = envelope.output;
    if (output.status === 'rejected' || output.status === 'failed') {
      const code = output.code === 'query_not_found' ? 'QUERY_NOT_READY' : 'SEARCH_REJECTED';
      const message = code === 'QUERY_NOT_READY'
        ? 'This demo query has not been indexed. Run the hybrid-search notebook and retry.'
        : 'The PIM backend rejected this search.';
      return searchFailure(code, message);
    }
    const queryTerms = output.queryTerms;
    const rankedItems = output.items;
    if (output.queryId !== queryId || typeof output.label !== 'string'
      || typeof output.queryText !== 'string' || !Array.isArray(queryTerms)
      || !queryTerms.every((term) => typeof term === 'string')
      || output.embeddingDimensions !== 1536
      || output.ranking !== 'RRF(DiskANN cosine, BM25)'
      || !Array.isArray(rankedItems) || !rankedItems.every(validRankedItem)) {
      return searchFailure('INVALID_RESPONSE', 'The PIM backend returned an unexpected search response.');
    }
    const backendFreshness = freshness(output);
    const hydrated = await hydrate(rankedItems, status, ownerToken, request);
    const staleCount = backendFreshness.staleCount + hydrated.staleCount;
    const indexingPending = backendFreshness.indexingPending || staleCount > 0;
    return {
      ok: true,
      code: 'OK',
      message: `${hydrated.items.length} ranked products returned.${indexingPending ? ' Search indexing pending; browse the authoritative catalog for complete results.' : ''}`,
      staleCount, indexingPending,
      diagnostics: diagnostics(output),
      queryId,
      label: output.label,
      queryText: output.queryText,
      queryTerms,
      embeddingDimensions: output.embeddingDimensions,
      ranking: output.ranking,
      elapsedMs: Date.now() - startedAt,
      items: hydrated.items,
    };
  } catch (error) {
    return error instanceof Error && (error.name === 'TimeoutError' || error.name === 'AbortError')
      ? searchFailure('SEARCH_TIMEOUT', 'Hybrid search timed out. Try again.')
      : searchFailure('SEARCH_UNAVAILABLE', 'Hybrid search is unavailable. Check the connection and retry.');
  }
}

export async function searchCatalogByName(
  queryText: string,
  status: string,
  ownerToken: string,
  request: typeof fetch = fetch,
): Promise<NameSearchResult> {
  if (!validNameQuery(queryText) || !validStatus(status)) {
    return {
      diagnostics: diagnostics(),
      staleCount: 0, indexingPending: false,
      ok: false,
      code: 'INVALID_SEARCH',
      message: 'Enter at least two characters of a product name.',
      queryText: '',
      queryTerms: [],
      ranking: '',
      elapsedMs: 0,
      items: [],
    };
  }
  if (!ownerToken) {
    return {
      diagnostics: diagnostics(),
      staleCount: 0, indexingPending: false,
      ok: false,
      code: 'OWNER_TOKEN_UNAVAILABLE',
      message: 'The app owner connection is unavailable.',
      queryText: '',
      queryTerms: [],
      ranking: '',
      elapsedMs: 0,
      items: [],
    };
  }
  const normalizedQuery = queryText.trim();
  const startedAt = Date.now();
  try {
    const response = await request(udfUrl('search_products_by_name'), {
      method: 'POST',
      headers: {
        Authorization: ['Bearer', ownerToken].join(' '),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ queryText: normalizedQuery, pageSize: 10, status }),
      signal: AbortSignal.timeout(25_000),
      redirect: 'error',
    });
    if (!response.ok) {
      await response.body?.cancel();
      return {
        diagnostics: diagnostics(),
        staleCount: 0, indexingPending: false,
        ok: false,
        code: 'SEARCH_UNAVAILABLE',
        message: 'Name search is unavailable. Check the published PIM backend and retry.',
        queryText: normalizedQuery,
        queryTerms: [],
        ranking: '',
        elapsedMs: 0,
        items: [],
      };
    }
    const envelope = await readBody(response);
    if (!isRecord(envelope) || envelope.status !== 'Succeeded'
      || envelope.functionName !== 'search_products_by_name'
      || !Array.isArray(envelope.errors) || envelope.errors.length !== 0
      || !isRecord(envelope.output)) {
      throw new TypeError('Invalid name-search response.');
    }
    const output = envelope.output;
    const queryTerms = output.queryTerms;
    const rankedItems = output.items;
    if (output.status === 'rejected' || output.status === 'failed'
      || output.queryText !== normalizedQuery
      || !Array.isArray(queryTerms)
      || !queryTerms.every((term) => typeof term === 'string')
      || output.ranking !== 'BM25 with product-name filter'
      || !Array.isArray(rankedItems)
      || !rankedItems.every(validRankedItem)) {
      throw new TypeError('Invalid name-search response.');
    }
    const backendFreshness = freshness(output);
    const hydrated = await hydrate(rankedItems, status, ownerToken, request);
    const staleCount = backendFreshness.staleCount + hydrated.staleCount;
    const indexingPending = backendFreshness.indexingPending || staleCount > 0;
    return {
      ok: true,
      code: 'OK',
      message: `${hydrated.items.length} product name matches returned.${indexingPending ? ' Search indexing pending; browse the authoritative catalog for complete results.' : ''}`,
      staleCount, indexingPending,
      diagnostics: diagnostics(output),
      queryText: normalizedQuery,
      queryTerms,
      ranking: output.ranking,
      elapsedMs: Date.now() - startedAt,
      items: hydrated.items,
    };
  } catch (error) {
    const timeout = error instanceof Error
      && (error.name === 'TimeoutError' || error.name === 'AbortError');
    return {
      diagnostics: diagnostics(),
      staleCount: 0, indexingPending: false,
      ok: false,
      code: timeout ? 'SEARCH_TIMEOUT' : 'SEARCH_UNAVAILABLE',
      message: timeout
        ? 'Name search timed out. Try again.'
        : 'Name search is unavailable. Check the connection and retry.',
      queryText: normalizedQuery,
      queryTerms: [],
      ranking: '',
      elapsedMs: 0,
      items: [],
    };
  }
}
