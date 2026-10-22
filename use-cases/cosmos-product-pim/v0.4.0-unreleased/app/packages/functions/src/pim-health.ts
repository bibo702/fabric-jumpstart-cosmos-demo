import { listProducts } from './pim-catalog.js';
import { searchCatalog } from './pim-search.js';

export interface BackendProbe {
  readProbe: 'passed' | 'failed';
  searchProbe: 'passed' | 'pending' | 'failed';
  searchEnabled: boolean;
}

export async function probeBackend(token: string, request: typeof fetch = fetch): Promise<BackendProbe> {
  const read = await listProducts(1, '', token, request);
  const search = await searchCatalog('lightweight-shelter', 'active', token, request);
  return {
    readProbe: read.ok ? 'passed' : 'failed',
    searchProbe: !search.ok ? 'failed' : search.indexingPending ? 'pending' : 'passed',
    searchEnabled: search.ok,
  };
}
