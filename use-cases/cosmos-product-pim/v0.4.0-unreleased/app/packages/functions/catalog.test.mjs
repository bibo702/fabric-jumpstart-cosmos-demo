import assert from 'node:assert/strict';
import { test } from 'node:test';
import './test-config.mjs';
import { createProduct } from './dist/pim-actions.js';
import { listProducts, getSearchIndexStatus } from './dist/pim-catalog.js';
import { searchCatalogByName, searchCatalog } from './dist/pim-search.js';
import { configured, getConfig } from './dist/config.js';
import { probeBackend } from './dist/pim-health.js';
const product = { productId: 'a', name: 'A product', description: 'Description', categoryName: 'Category', status: 'active', version: 2 };
const envelope = (functionName, output) => Response.json({ functionName, output, errors: [], status: 'Succeeded' });
const creation = { productId: 'new', operationId: '00000000-0000-4000-8000-000000000001', reason: 'New catalog entry', name: 'New', description: 'Description', categoryName: 'Category' };

test('authoritative browsing is paginated, validates order, and never calls search', async () => {
  const result = await listProducts(20, '', 'owner', async (url, options) => {
    assert.ok(url.endsWith('/list_products/invoke'));
    assert.deepEqual(JSON.parse(options.body), { pageSize: 20, afterProductId: '' });
    return envelope('list_products', { items: [{ ...product, secret: 'private' }], afterProductId: 'a' });
  });
  assert.equal(result.ok, true);
  assert.deepEqual(result.items, [product]);
  assert.equal(result.afterProductId, 'a');
  for (const output of [{ items: [product], afterProductId: 'wrong' }, { items: [product, product], afterProductId: '' }]) {
    assert.equal((await listProducts(20, '', 'owner', async () => envelope('list_products', output))).ok, false);
  }
  assert.equal((await listProducts(0, '', 'owner', async () => assert.fail('No request'))).ok, false);
  assert.equal((await listProducts(20, 'a', 'owner', async () => envelope('list_products', { items: [product], afterProductId: '' }))).ok, false);
});

test('creation uses one atomic backend call and fixed initial version with replay support', async () => {
  const result = await createProduct(creation, 'owner', async (url, options) => {
    assert.ok(url.endsWith('/create_product/invoke'));
    assert.deepEqual(JSON.parse(options.body), { payload: creation });
    return envelope('create_product', { status: 'applied', productId: 'new', version: 1, eventId: `event:${creation.operationId}`, replayed: true, indexingPending: true });
  });
  assert.equal(result.ok, true);
  assert.equal(result.replayed, true);
  assert.equal(result.indexingPending, true);
  for (const code of ['already_exists', 'operation_conflict']) {
    assert.equal((await createProduct(creation, 'owner', async () => envelope('create_product', { status: 'rejected', code }))).code, code);
  }
  assert.equal((await createProduct({ ...creation, priceMinor: 500 }, 'owner', async () => assert.fail('No request'))).outcome, 'rejected');
  assert.equal((await createProduct(creation, 'owner', async () => { throw Error('private'); })).outcome, 'unknown');
});

test('search races drop mismatching version and status and report pending indexing for both endpoints', async () => {
  for (const mode of ['name', 'preset']) {
    for (const changed of [{ version: 3 }, { status: 'deleted' }]) {
      const request = async (url) => url.endsWith('/get_product/invoke')
        ? envelope('get_product', { ...product, ...changed })
        : envelope(mode === 'name' ? 'search_products_by_name' : 'search_products_by_query', {
          queryText: mode === 'name' ? 'product' : 'preset text', queryTerms: ['product'], queryId: 'lightweight-shelter', label: 'Preset', embeddingDimensions: 1536,
          ranking: mode === 'name' ? 'BM25 with product-name filter' : 'RRF(DiskANN cosine, BM25)',
          staleCount: 2, indexingPending: false, items: [{ productId: 'a', sourceVersion: 2, status: 'active' }],
        });
      const result = mode === 'name' ? await searchCatalogByName('product', 'active', 'owner', request) : await searchCatalog('lightweight-shelter', 'active', 'owner', request);
      assert.equal(result.ok, true);
      assert.equal(result.items.length, 0);
      assert.equal(result.staleCount, 3);
      assert.equal(result.indexingPending, true);
    }
  }
});

test('freshness checks validate versions, complete requested IDs, and pending counts', async () => {
  const output = { items: [{ productId: 'a', version: 2, sourceVersion: 1, status: 'pending' }], pendingCount: 1 };
  assert.equal((await getSearchIndexStatus(['a'], 'owner', async () => envelope('get_search_index_status', output))).pendingCount, 1);
  assert.equal((await getSearchIndexStatus(['a'], 'owner', async () => envelope('get_search_index_status', { ...output, pendingCount: 0 }))).ok, false);
  assert.equal((await getSearchIndexStatus(['a'], 'owner', async () => envelope('get_search_index_status', { items: [{ ...output.items[0], status: 'current' }], pendingCount: 0 }))).ok, false);
});

test('configuration has no fallback target and rejects non-Fabric or inconsistent endpoints', () => {
  assert.equal(configured(), true);
  const previous = process.env.PIM_RAYFIN_ENDPOINT;
  try {
    for (const value of ['', 'https://evil.example/', `${previous}?token=private`, previous.replace('55555555', '88888888')]) {
      process.env.PIM_RAYFIN_ENDPOINT = value;
      assert.equal(configured(), false);
      assert.throws(getConfig);
    }
  } finally { process.env.PIM_RAYFIN_ENDPOINT = previous; }
});

test('health uses real list and preset reads and distinguishes failed and pending probes', async () => {
  const urls = [];
  const result = await probeBackend('owner', async (url) => {
    urls.push(url);
    if (url.endsWith('/list_products/invoke')) return envelope('list_products', { items: [product], afterProductId: '' });
    return envelope('search_products_by_query', {
      queryId: 'lightweight-shelter', label: 'Preset', queryText: 'preset', queryTerms: ['preset'],
      embeddingDimensions: 1536, ranking: 'RRF(DiskANN cosine, BM25)', items: [], staleCount: 1, indexingPending: true,
    });
  });
  assert.equal(urls.length, 2);
  assert.deepEqual(result, { readProbe: 'passed', searchProbe: 'pending', searchEnabled: true });
  const failed = await probeBackend('owner', async () => new Response('private', { status: 403 }));
  assert.deepEqual(failed, { readProbe: 'failed', searchProbe: 'failed', searchEnabled: false });
});

test('catalog accepts full-document pages above 64 KiB and rejects pages above its explicit 2 MiB bound', async () => {
  const items = Array.from({ length: 20 }, (_, index) => ({
    ...product, productId: `product-${String(index).padStart(2, '0')}`,
    description: 'd'.repeat(4_000), metadata: { source: 'm'.repeat(2_000) },
  }));
  const output = { items, afterProductId: 'product-19' };
  assert.ok(Buffer.byteLength(JSON.stringify(output)) > 65_536);
  const result = await listProducts(20, '', 'owner', async () => envelope('list_products', output));
  assert.equal(result.ok, true);
  assert.equal(result.items.length, 20);
  assert.equal(result.items[19].description.length, 4_000);
  assert.equal(Object.hasOwn(result.items[0], 'metadata'), false);
  const oversized = await listProducts(20, '', 'owner', async () => envelope('list_products', {
    items: [{ ...product, metadata: 'm'.repeat(2_097_152) }], afterProductId: '',
  }));
  assert.equal(oversized.ok, false);
});

test('missing request-charge telemetry remains null while an explicitly supplied zero remains zero', async () => {
  for (const [diagnostics, expected] of [[undefined, null], [{ scope: 'search-query-only' }, null],
    [{ scope: 'search-query-only', requestCharge: null }, null],
    [{ scope: 'search-query-only', requestCharge: 0 }, 0]]) {
    const result = await searchCatalogByName('product', 'active', 'owner', async () => envelope('search_products_by_name', {
      queryText: 'product', queryTerms: ['product'], ranking: 'BM25 with product-name filter',
      items: [], staleCount: 0, indexingPending: false, diagnostics,
    }));
    assert.equal(result.ok, true);
    assert.equal(result.diagnostics.requestCharge, expected);
    assert.deepEqual(result.diagnostics.queryMetrics, []);
    assert.deepEqual(result.diagnostics.indexMetrics, []);
  }
});
