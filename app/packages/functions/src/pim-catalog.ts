import { invoke } from './pim-actions.js';
import { isRecord, projectProduct, validProduct, type ProductSummary } from './pim.js';

export interface CatalogPage {
  ok: boolean;
  message: string;
  items: ProductSummary[];
  afterProductId: string;
}

export interface IndexStatus {
  ok: boolean;
  message: string;
  items: { productId: string; sourceVersion: number | null; version: number; status: 'current' | 'pending' }[];
  pendingCount: number;
}

const idPattern = /^[a-zA-Z0-9_-]{1,100}$/;

export async function listProducts(pageSize: number, afterProductId: string, token: string, request: typeof fetch = fetch): Promise<CatalogPage> {
  const failure: CatalogPage = { ok: false, message: 'Authoritative catalog unavailable. Check configuration and read grants, then retry.', items: [], afterProductId: '' };
  if (!Number.isSafeInteger(pageSize) || pageSize < 1 || pageSize > 100
    || typeof afterProductId !== 'string' || (afterProductId !== '' && !idPattern.test(afterProductId)) || !token) return failure;
  try {
    const output = await invoke('list_products', { pageSize, afterProductId }, token, request);
    if (!Array.isArray(output.items) || output.items.length > pageSize
      || !output.items.every(validProduct) || typeof output.afterProductId !== 'string'
      || (output.afterProductId !== '' && (!idPattern.test(output.afterProductId)
        || output.afterProductId !== output.items.at(-1)?.productId))
      || output.items.some((item, index, items) => item.productId <= (index ? items[index - 1].productId : afterProductId))) return failure;
    return { ok: true, message: 'Authoritative catalog page loaded.', items: output.items.map(projectProduct), afterProductId: output.afterProductId };
  } catch { return failure; }
}

export async function getSearchIndexStatus(productIds: string[], token: string, request: typeof fetch = fetch): Promise<IndexStatus> {
  const failure: IndexStatus = { ok: false, message: 'Search freshness unavailable; indexing is not verified.', items: [], pendingCount: 0 };
  if (!Array.isArray(productIds) || productIds.length < 1 || productIds.length > 100
    || !productIds.every((id) => typeof id === 'string' && idPattern.test(id))
    || new Set(productIds).size !== productIds.length || !token) return failure;
  try {
    const output = await invoke('get_search_index_status', { productIds }, token, request);
    if (!Array.isArray(output.items) || output.items.length !== productIds.length) return failure;
    const items: IndexStatus['items'] = [];
    for (const item of output.items) {
      if (!isRecord(item) || typeof item.productId !== 'string' || !productIds.includes(item.productId)
        || items.some((entry) => entry.productId === item.productId)
        || typeof item.version !== 'number' || !Number.isSafeInteger(item.version) || item.version < 1
        || !(item.sourceVersion === null || (typeof item.sourceVersion === 'number' && Number.isSafeInteger(item.sourceVersion) && item.sourceVersion > 0))
        || (item.status !== 'current' && item.status !== 'pending')
        || (item.status === 'current' && item.sourceVersion !== item.version)) return failure;
      items.push({ productId: item.productId, version: item.version, sourceVersion: item.sourceVersion, status: item.status });
    }
    const pendingCount = items.filter((item) => item.status === 'pending').length;
    if (output.pendingCount !== pendingCount) return failure;
    return { ok: true, message: 'Freshness is a point-in-time comparison, not a guarantee against subsequent edits.', items, pendingCount };
  } catch { return failure; }
}
