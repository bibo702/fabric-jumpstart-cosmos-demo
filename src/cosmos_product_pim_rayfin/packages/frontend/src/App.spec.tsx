//-----------------------------------------------------------------------
// <copyright company="Microsoft Corporation">
//        Copyright (c) Microsoft Corporation.  All rights reserved.
//        Licensed under the MIT license. See LICENSE file in the project root for full license information.
// </copyright>
//-----------------------------------------------------------------------

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, it, expect, vi } from 'vitest';

const calls = vi.hoisted(() => ({
  product: vi.fn(),
  connection: vi.fn(),
  history: vi.fn(),
  save: vi.fn(),
  search: vi.fn(),
}));
vi.mock('./lib/rayfin-client', () => ({
  getRayfinClient: async () => ({ functions: {
    getProduct: { invoke: calls.product }, getConnectionStatus: { invoke: calls.connection },
    getHistory: { invoke: calls.history }, saveProduct: { invoke: calls.save },
    searchCatalog: { invoke: calls.search },
  } }),
}));

// The welcome view polls a dev-only activity endpoint via `useSourceActivity`.
// In this smoke test there is no dev server, so stub the hook to return no feed:
// the view renders its illustrative state synchronously and nothing settles after
// the test (which would otherwise log a React `act(...)` warning).
vi.mock('./Welcome.activity', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./Welcome.activity')>();
  return { ...actual, useSourceActivity: () => null };
});

import App from '@/App';

describe('App', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    sessionStorage.clear();
    calls.connection.mockResolvedValue({
      authorized: true,
      backend: 'PIMv2_ProductPimBackend',
      writesEnabled: true,
      searchEnabled: true,
    });
    calls.history.mockResolvedValue({ ok: true, message: 'History loaded.', items: [], continuationToken: '' });
    calls.product.mockResolvedValue({ ok: false, code: 'BACKEND_UNAVAILABLE', message: 'PIMv2 rejected the read request.', product: null });
    calls.search.mockResolvedValue({
      ok: true,
      code: 'OK',
      message: 'Hybrid search completed.',
      queryId: 'lightweight-shelter',
      label: 'Lightweight shelter',
      queryText: 'lightweight shelter for two campers',
      queryTerms: ['lightweight', 'shelter', 'two', 'campers'],
      embeddingDimensions: 1536,
      ranking: 'RRF(DiskANN cosine, BM25)',
      elapsedMs: 42,
      items: [],
    });
  });
  it('renders without throwing', () => {
    expect(() => render(<App />)).not.toThrow();
  });

  it('mounts content into the document', () => {
    render(<App />);
    expect(document.body).not.toBeEmptyDOMElement();
  });

  it('shows no invented products and exposes no write controls', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'Product catalog' })).toBeInTheDocument();
    expect(screen.getByText('No product selected.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Look up product' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument();
  });

  it('opens connection status without inventing verified write permissions', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Connection' }));
    expect(screen.getByRole('heading', { name: 'Backend connection' })).toBeInTheDocument();
    expect(screen.getByText('Not checked')).toBeInTheDocument();
  });

  it('shows a safe read failure without claiming a connection succeeded', async () => {
    render(<App />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Product ID' }), { target: { value: 'test-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Look up product' }));
    expect(await screen.findByText('PIMv2 rejected the read request.')).toBeInTheDocument();
    expect(calls.product).toHaveBeenCalledWith({ productId: 'test-1' }, { timeoutMs: 35_000 });
    expect(screen.queryByRole('region', { name: 'Product details' })).not.toBeInTheDocument();
  });

  it('renders successful reads and clears stale results when the ID changes', async () => {
    calls.product.mockResolvedValueOnce({ ok: true, message: 'Product loaded.', code: 'OK', product: {
      productId: 'test-1', name: 'Test product', description: 'Test description', categoryName: 'Test', status: 'deleted', version: 2,
    } });
    render(<App />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Product ID' }), { target: { value: 'test-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Look up product' }));
    expect(await screen.findByRole('heading', { name: 'Test product' })).toBeInTheDocument();
    expect(screen.getByText('Archived')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: 'Product ID' }), { target: { value: 'other' } });
    expect(screen.queryByRole('region', { name: 'Product details' })).not.toBeInTheDocument();
  });

  it('handles unexpected failures without exposing exception details', async () => {
    calls.product.mockRejectedValueOnce(new Error('secret-value'));
    render(<App />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Product ID' }), { target: { value: 'test-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Look up product' }));
    expect(await screen.findByText(/Product read unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/secret-value/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Look up product' })).toBeEnabled();
  });

  it('verifies the account without claiming a product read succeeded', async () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Connection' }));
    fireEvent.click(screen.getByRole('button', { name: 'Check account' }));
    expect(await screen.findByText('Account verified. Product and search operations are checked separately.')).toBeInTheDocument();
    expect(screen.getByText('App owner')).toBeInTheDocument();
    expect(screen.getByText('Not verified')).toBeInTheDocument();
    expect(screen.getByText('Enabled; PIMv2 enforces permissions')).toBeInTheDocument();
  });

  it('reports a rejected account', async () => {
    calls.connection.mockResolvedValueOnce({
      authorized: false,
      backend: 'PIMv2_ProductPimBackend',
      writesEnabled: false,
      searchEnabled: false,
    });
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Connection' }));
    fireEvent.click(screen.getByRole('button', { name: 'Check account' }));
    expect(await screen.findByText('Access denied for this account.')).toBeInTheDocument();
  });

  const product = { productId: 'test-1', name: 'Test product', description: 'Test description', categoryName: 'Test', status: 'active', version: 2 };
  async function openProduct(status = 'active') {
    calls.product.mockResolvedValueOnce({ ok: true, message: 'Product loaded.', code: 'OK', product: { ...product, status } });
    render(<App />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Product ID' }), { target: { value: 'test-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Look up product' }));
    await screen.findByRole('heading', { name: 'Test product' });
  }

  it('saves changed fields with a reason and optimistic version then reloads', async () => {
    await openProduct();
    calls.save.mockResolvedValue({ ok: true, outcome: 'applied', code: 'OK', message: 'Change saved.', version: 3, replayed: false });
    calls.product.mockResolvedValue({ ok: true, message: 'Product loaded.', product: { ...product, name: 'New name', version: 3 } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'New name' } });
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: 'Reason for change' }), { target: { value: 'Correct product name' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByText('Version 3')).toBeInTheDocument();
    expect(calls.save).toHaveBeenCalledWith({ payload: { productId: 'test-1', expectedVersion: 2, operationId: expect.any(String), reason: 'Correct product name', changes: { name: 'New name' } } }, { timeoutMs: 40_000 });
    expect(sessionStorage.getItem('pim-pending:test-1')).toBeNull();
  });

  it('retries an uncertain outcome with the exact original payload', async () => {
    await openProduct();
    calls.save.mockResolvedValue({ ok: false, outcome: 'unknown', code: 'OUTCOME_UNKNOWN', message: 'Outcome unknown', version: 0, replayed: false });
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'New name' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Reason for change' }), { target: { value: 'Correction' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await screen.findByText('Outcome unknown');
    const original = calls.save.mock.calls[0][0];
    expect(JSON.parse(sessionStorage.getItem('pim-pending:test-1') ?? '{}')).toEqual(original.payload);
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Retry pending save' }));
    await waitFor(() => expect(calls.save).toHaveBeenCalledTimes(2));
    expect(calls.save.mock.calls[1][0]).toEqual(original);
  });

  it('requires confirmation for a status-only archive', async () => {
    await openProduct();
    calls.save.mockResolvedValue({ ok: true, outcome: 'applied', code: 'OK', message: 'Change saved.', version: 3, replayed: false });
    calls.product.mockResolvedValue({ ok: true, message: 'Product loaded.', product: { ...product, status: 'deleted', version: 3 } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Reason for change' }), { target: { value: 'Retire product' } });
    fireEvent.click(screen.getByRole('button', { name: 'Archive product' }));
    expect(calls.save).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm archive' }));
    await screen.findByText('Archived');
    expect(calls.save.mock.calls[0][0].payload.changes).toEqual({ status: 'deleted' });
  });

  it('allows status-only restoration and prevents content edits while archived', async () => {
    await openProduct('deleted');
    expect(screen.getByRole('textbox', { name: 'Name' })).toBeDisabled();
    calls.save.mockResolvedValue({ ok: true, outcome: 'applied', code: 'OK', message: 'Change saved.', version: 3, replayed: false });
    calls.product.mockResolvedValue({ ok: true, message: 'Product loaded.', product: { ...product, version: 3 } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Reason for change' }), { target: { value: 'Return to catalog' } });
    fireEvent.click(screen.getByRole('button', { name: 'Restore product' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm restore' }));
    await screen.findByText('Active');
    expect(calls.save.mock.calls[0][0].payload.changes).toEqual({ status: 'active' });
  });

  it('shows recorded actors and before/after values and loads older history', async () => {
    calls.history.mockResolvedValueOnce({ ok: true, message: 'Loaded', continuationToken: 'older', items: [{ id: 'event-1', action: 'ProductUpdated', occurredAt: '2026-10-06T12:00:00Z', fromVersion: 1, toVersion: 2, actor: { username: 'editor@example.com', oid: 'editor-id', tenantId: 'tenant' }, reason: 'Rename product', operationId: 'operation', changes: [{ path: '/name', oldValue: 'Old name', newValue: 'Test product' }] }] });
    await openProduct();
    expect(await screen.findByText('editor@example.com')).toBeInTheDocument();
    expect(screen.getByText('Old name')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Load older changes' }));
    await waitFor(() => expect(calls.history).toHaveBeenCalledWith({ productId: 'test-1', continuationToken: 'older' }, { timeoutMs: 35_000 }));
  });

  it('blocks editing on a version conflict until an authoritative reload', async () => {
    await openProduct();
    calls.save.mockResolvedValue({ ok: false, outcome: 'rejected', code: 'version_conflict', message: 'Product changed.', version: 0, replayed: false });
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'New name' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Reason for change' }), { target: { value: 'Correction' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await screen.findByText('Product changed.');
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reload product' })).toBeEnabled();
    expect(sessionStorage.getItem('pim-pending:test-1')).toBeNull();
  });

  it('runs the selected stored-query preset and renders Cosmos ranking details', async () => {
    calls.search.mockResolvedValueOnce({
      ok: true,
      code: 'OK',
      message: 'Hybrid search completed.',
      queryId: 'trail-riding',
      label: 'Trail riding',
      queryText: 'bicycle for riding on outdoor trails',
      queryTerms: ['bicycle', 'riding', 'outdoor', 'trails'],
      embeddingDimensions: 1536,
      ranking: 'RRF(DiskANN cosine, BM25)',
      elapsedMs: 37,
      items: [{
        rank: 1,
        sourceVersion: 4,
        productId: 'bike-100',
        name: 'Trail bike',
        description: 'A bike for trails.',
        categoryName: 'Cycling',
        status: 'active',
        version: 4,
      }],
    });
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Trail riding/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Run hybrid search' }));
    expect(await screen.findByText('Trail bike')).toBeInTheDocument();
    expect(calls.search).toHaveBeenCalledWith(
      { queryId: 'trail-riding', status: 'active' },
      { timeoutMs: 45_000 },
    );
    expect(screen.getByText('37 ms bridge time')).toBeInTheDocument();
    expect(screen.getByText('1,536 dimensions')).toBeInTheDocument();
    expect(screen.getByText('RRF(DiskANN cosine, BM25)')).toBeInTheDocument();
  });

  it('opens an authoritative product after selecting a ranked result', async () => {
    calls.search.mockResolvedValueOnce({
      ok: true,
      code: 'OK',
      message: 'Hybrid search completed.',
      queryId: 'lightweight-shelter',
      label: 'Lightweight shelter',
      queryText: 'lightweight shelter for two campers',
      queryTerms: ['lightweight', 'shelter', 'campers'],
      embeddingDimensions: 1536,
      ranking: 'RRF(DiskANN cosine, BM25)',
      elapsedMs: 30,
      items: [{
        rank: 1,
        sourceVersion: 2,
        productId: 'tent-100',
        name: 'Two-person tent',
        description: 'Light shelter.',
        categoryName: 'Camping',
        status: 'active',
        version: 2,
      }],
    });
    calls.product.mockResolvedValueOnce({
      ok: true,
      code: 'OK',
      message: 'Product loaded.',
      product: { ...product, productId: 'tent-100', name: 'Two-person tent' },
    });
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Run hybrid search' }));
    fireEvent.click(await screen.findByRole('button', { name: /Two-person tent/ }));
    expect(await screen.findByRole('heading', { name: 'Two-person tent' })).toBeInTheDocument();
    expect(calls.product).toHaveBeenCalledWith(
      { productId: 'tent-100' },
      { timeoutMs: 35_000 },
    );
  });

  it('explains the Fabric-only preset architecture before search', () => {
    render(<App />);
    expect(screen.getAllByText(/ai\.embed/)).toHaveLength(2);
    expect(screen.getByText(/keeping this demo Fabric-only/)).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Hybrid search pipeline' })).toBeInTheDocument();
    expect(screen.getByText('No duplicate catalog')).toBeInTheDocument();
  });

  it('shows a safe hybrid-search failure', async () => {
    calls.search.mockRejectedValueOnce(new Error('private backend detail'));
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Run hybrid search' }));
    expect(await screen.findByText(/Hybrid search is unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/private backend detail/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run hybrid search' })).toBeEnabled();
  });

  it('recovers an unconfirmed operation from session storage without generating a new ID', async () => {
    const pending = { productId: 'test-1', expectedVersion: 1, operationId: '00000000-0000-4000-8000-000000000001', reason: 'Correction', changes: { name: 'Original pending name' } };
    sessionStorage.setItem('pim-pending:test-1', JSON.stringify(pending));
    calls.save.mockResolvedValue({ ok: false, outcome: 'unknown', code: 'OUTCOME_UNKNOWN', message: 'Outcome unknown', version: 0, replayed: false });
    await openProduct();
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Retry pending save' }));
    await waitFor(() => expect(calls.save).toHaveBeenCalledWith({ payload: pending }, { timeoutMs: 40_000 }));
  });
});
