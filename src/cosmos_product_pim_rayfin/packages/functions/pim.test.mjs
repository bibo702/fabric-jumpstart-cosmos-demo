import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readProduct } from './dist/pim.js';
import { updateProduct, readHistory } from './dist/pim-actions.js';
import { searchCatalog } from './dist/pim-search.js';

const product = {
  productId: 'test-1', name: 'Test product', description: 'Test description',
  categoryName: 'Test', status: 'active', version: 1,
};
const response = output => Response.json({ functionName: 'get_product', status: 'Succeeded', output, errors: [] });

test('reads only the fixed get_product endpoint and projects approved fields', async () => {
  const result = await readProduct('test-1', 'test-token', async (url, options) => {
    assert.equal(new URL(url).hostname, 'api.fabric.microsoft.com');
    assert.ok(url.endsWith('/758636a3-bb2b-4071-bdc8-ba739e611efd/functions/get_product/invoke'));
    assert.equal(options.method, 'POST');
    assert.equal(options.redirect, 'error');
    assert.deepEqual(JSON.parse(options.body), { productId: 'test-1' });
    assert.equal(options.headers.Authorization, 'Bearer test-token');
    assert.ok(options.signal instanceof AbortSignal);
    return response({ ...product, internalValue: 'must not escape' });
  });
  assert.equal(result.ok, true);
  assert.deepEqual(result.product, product);
  assert.ok(!JSON.stringify(result).includes('test-token'));
});

test('rejects invalid IDs and absent owner tokens without a backend request', async () => {
  const unexpected = async () => assert.fail('No request expected');
  for (const productId of ['', '../seed_catalog', 'a'.repeat(101), null]) {
    assert.equal((await readProduct(productId, 'test-token', unexpected)).code, 'INVALID_PRODUCT_ID');
  }
  assert.equal((await readProduct('test-1', '', unexpected)).code, 'OWNER_TOKEN_UNAVAILABLE');
});

test('maps missing products without returning backend messages', async () => {
  const result = await readProduct('test-1', 'test-token', async () => response({ status: 'rejected', code: 'not_found', message: 'private' }));
  assert.equal(result.code, 'NOT_FOUND');
  assert.ok(!JSON.stringify(result).includes('private'));
});

test('rejects mismatched products and invalid versions', async () => {
  for (const change of [{ productId: 'other' }, { version: -1 }, { status: 'unknown' }, { name: null }]) {
    assert.equal((await readProduct('test-1', 'test-token', async () => response({ ...product, ...change }))).code, 'INVALID_RESPONSE');
  }
});

test('sanitizes HTTP failures, malformed data, failed envelopes, and oversized responses', async () => {
  for (const makeResponse of [
    () => new Response('private', { status: 500 }),
    () => new Response('not json'),
    () => Response.json({ status: 'Failed', errors: ['private'] }),
    () => new Response('x'.repeat(65_537)),
  ]) {
    const result = await readProduct('test-1', 'test-token', async () => makeResponse());
    assert.equal(result.ok, false);
    assert.equal(result.product, null);
    assert.ok(!JSON.stringify(result).includes('private'));
  }
});

test('sanitizes timeouts and network errors', async () => {
  for (const [error, code] of [[new DOMException('private', 'TimeoutError'), 'READ_TIMEOUT'], [new Error('private'), 'BACKEND_UNAVAILABLE']]) {
    const result = await readProduct('test-1', 'test-token', async () => { throw error; });
    assert.equal(result.code, code);
    assert.ok(!JSON.stringify(result).includes('private'));
  }
});

const mutation = { productId: 'test-1', expectedVersion: 1, operationId: '00000000-0000-4000-8000-000000000001', reason: 'Catalog correction', changes: { name: 'Updated product' } };
const actionResponse = (functionName, output) => Response.json({ functionName, status: 'Succeeded', output, errors: [] });

test('writes only approved fields to PIMv2 and preserves operation ID and version', async () => {
  const result = await updateProduct(mutation, 'test-token', async (url, options) => {
    assert.ok(url.endsWith('/functions/update_product/invoke'));
    assert.deepEqual(JSON.parse(options.body), { payload: mutation });
    return actionResponse('update_product', { status: 'applied', productId: 'test-1', version: 2, eventId: `event:${mutation.operationId}`, replayed: true });
  });
  assert.equal(result.ok, true);
  assert.equal(result.replayed, true);
  assert.equal(result.version, 2);
});

test('invalid mutation fields and mixed status edits never invoke the backend', async () => {
  for (const change of [{ reason: '' }, { expectedVersion: 0 }, { operationId: 'bad' }, { changes: { price: 1 } }, { changes: { status: 'deleted', name: 'Test' } }, { changes: {} }]) {
    const result = await updateProduct({ ...mutation, ...change }, 'test-token', async () => assert.fail('No request expected'));
    assert.equal(result.outcome, 'rejected');
  }
});

test('conflicts are definitive while transport or malformed save responses remain uncertain', async () => {
  const conflict = await updateProduct(mutation, 'test-token', async () => actionResponse('update_product', { status: 'rejected', code: 'version_conflict', message: 'private' }));
  assert.equal(conflict.code, 'version_conflict');
  assert.equal(conflict.outcome, 'rejected');
  for (const request of [async () => { throw new Error('private'); }, async () => actionResponse('update_product', { status: 'failed' }), async () => new Response('private', { status: 500 })]) {
    const result = await updateProduct(mutation, 'test-token', request);
    assert.equal(result.outcome, 'unknown');
    assert.ok(!JSON.stringify(result).includes('private'));
  }
});

test('history preserves actor, reason and before/after values while stripping internal data', async () => {
  const event = { id: 'event:test', docType: 'auditEvent', productId: 'test-1', action: 'ProductUpdated', occurredAt: '2026-10-06T12:00:00Z', fromVersion: 1, toVersion: 2, actor: { oid: 'actor-id', tenantId: 'tenant-id', username: 'test@example.com', secret: 'private' }, reason: 'Correction', operationId: mutation.operationId, changes: [{ path: '/name', oldValue: 'Before', newValue: 'After' }] };
  const result = await readHistory('test-1', '', 'test-token', async (url, options) => {
    assert.ok(url.endsWith('/functions/get_history/invoke'));
    assert.deepEqual(JSON.parse(options.body), { productId: 'test-1', pageSize: 20, continuationToken: '' });
    return actionResponse('get_history', { items: [event], continuationToken: 'next-page' });
  });
  assert.equal(result.ok, true);
  assert.equal(result.items[0].actor.username, 'test@example.com');
  assert.deepEqual(result.items[0].changes, event.changes);
  assert.equal(result.continuationToken, 'next-page');
  assert.ok(!JSON.stringify(result).includes('private'));
});

test('malformed history and unbounded continuation tokens fail closed', async () => {
  assert.equal((await readHistory('test-1', 'x'.repeat(16001), 'test-token', async () => assert.fail('No request expected'))).ok, false);
  assert.equal((await readHistory('test-1', '', 'test-token', async () => actionResponse('get_history', { items: [{ productId: 'other' }], continuationToken: '' }))).ok, false);
});

test('creation history projects initial product fields from the seed snapshot', async () => {
  const event = { id: 'seed:test-1', docType: 'auditEvent', productId: 'test-1', action: 'ProductCreated', occurredAt: '2026-10-06T12:00:00Z', fromVersion: 0, toVersion: 1, actor: { oid: 'actor-id', tenantId: 'tenant-id' }, reason: 'Seed', operationId: 'seed:test-1', changes: [{ path: '/', oldValue: null, newValue: { productId: 'test-1', name: 'Initial', description: 'Description', categoryName: 'Category', status: 'active', private: 'hidden' } }] };
  const result = await readHistory('test-1', '', 'test-token', async () => actionResponse('get_history', { items: [event], continuationToken: '' }));
  assert.equal(result.ok, true);
  assert.equal(result.items[0].changes.length, 4);
  assert.deepEqual(result.items[0].changes[0], { path: '/name', oldValue: null, newValue: 'Initial' });
  assert.ok(!JSON.stringify(result).includes('hidden'));
});

test('hybrid search invokes the fixed preset endpoint and enriches ranked products', async () => {
  const searchOutput = {
    queryId: 'lightweight-shelter',
    label: 'Lightweight shelter',
    queryText: 'lightweight shelter for two campers',
    queryTerms: ['lightweight', 'shelter', 'for', 'two', 'campers'],
    embeddingDimensions: 1536,
    ranking: 'RRF(DiskANN cosine, BM25)',
    items: [{ productId: 'test-1', sourceVersion: 1, status: 'active' }],
  };
  const result = await searchCatalog(
    'lightweight-shelter',
    'active',
    'test-token',
    async (url, options) => {
      if (url.endsWith('/functions/search_products_by_query/invoke')) {
        assert.deepEqual(JSON.parse(options.body), {
          queryId: 'lightweight-shelter',
          pageSize: 10,
          status: 'active',
        });
        return actionResponse('search_products_by_query', searchOutput);
      }
      assert.ok(url.endsWith('/functions/get_product/invoke'));
      return response(product);
    },
  );
  assert.equal(result.ok, true);
  assert.equal(result.ranking, 'RRF(DiskANN cosine, BM25)');
  assert.equal(result.embeddingDimensions, 1536);
  assert.equal(result.items[0].rank, 1);
  assert.equal(result.items[0].name, 'Test product');
});

test('hybrid search rejects arbitrary queries and reports unindexed presets safely', async () => {
  const unexpected = async () => assert.fail('No request expected');
  assert.equal(
    (await searchCatalog('arbitrary-query', 'active', 'test-token', unexpected)).code,
    'INVALID_SEARCH',
  );
  const missing = await searchCatalog(
    'cycling-safety',
    'active',
    'test-token',
    async () => actionResponse(
      'search_products_by_query',
      { status: 'rejected', code: 'query_not_found', message: 'private storage detail' },
    ),
  );
  assert.equal(missing.code, 'QUERY_NOT_READY');
  assert.ok(!JSON.stringify(missing).includes('private'));
});

test('hybrid search fails closed on malformed ranking metadata', async () => {
  const result = await searchCatalog(
    'trail-riding',
    'all',
    'test-token',
    async () => actionResponse('search_products_by_query', {
      queryId: 'trail-riding',
      label: 'Trail riding',
      queryText: 'bicycle for riding on outdoor trails',
      queryTerms: ['bicycle'],
      embeddingDimensions: 3,
      ranking: 'fake',
      items: [],
    }),
  );
  assert.equal(result.code, 'INVALID_RESPONSE');
  assert.equal(result.items.length, 0);
});