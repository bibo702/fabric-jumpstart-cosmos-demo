import {
  PIM_UDF_BASE_URL,
  isRecord,
  readBody,
  readProduct,
  type ProductSummary,
} from './pim.js';

export type SearchStatus = 'all' | 'active' | 'deleted';

export interface SearchResultItem extends ProductSummary {
  rank: number;
  sourceVersion: number;
}

export interface CatalogSearchResult {
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

const SEARCH_URL = `${PIM_UDF_BASE_URL}/search_products_by_query/invoke`;
const QUERY_IDS = new Set([
  'lightweight-shelter',
  'cycling-safety',
  'trail-riding',
]);

export function searchFailure(code: string, message: string): CatalogSearchResult {
  return {
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

function validStatus(value: string): value is SearchStatus {
  return value === 'all' || value === 'active' || value === 'deleted';
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
    const response = await request(SEARCH_URL, {
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
    const products = await Promise.all(
      rankedItems.map((item) => readProduct(item.productId, ownerToken, request)),
    );
    if (products.some((product) => !product.ok || product.product === null)) {
      return searchFailure('PRODUCT_READ_FAILED', 'Search ranked products, but one or more catalog records could not be loaded.');
    }
    return {
      ok: true,
      code: 'OK',
      message: `${products.length} ranked product${products.length === 1 ? '' : 's'} returned.`,
      queryId,
      label: output.label,
      queryText: output.queryText,
      queryTerms,
      embeddingDimensions: output.embeddingDimensions,
      ranking: output.ranking,
      elapsedMs: Date.now() - startedAt,
      items: products.map((product, index) => ({
        ...product.product!,
        rank: index + 1,
        sourceVersion: rankedItems[index].sourceVersion,
      })),
    };
  } catch (error) {
    return error instanceof Error && (error.name === 'TimeoutError' || error.name === 'AbortError')
      ? searchFailure('SEARCH_TIMEOUT', 'Hybrid search timed out. Try again.')
      : searchFailure('SEARCH_UNAVAILABLE', 'Hybrid search is unavailable. Check the connection and retry.');
  }
}
