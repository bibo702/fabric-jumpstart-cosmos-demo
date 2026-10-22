import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const calls = vi.hoisted(() => ({ list: vi.fn(), index: vi.fn(), create: vi.fn() }));
vi.mock('./lib/rayfin-client', () => ({ getRayfinClient: async () => ({ functions: {
  listProducts: { invoke: calls.list }, getSearchIndexStatus: { invoke: calls.index }, createProduct: { invoke: calls.create },
} }) }));
import { Catalog } from './Catalog';
const product = { productId: 'a', name: 'Authoritative A', description: 'Description', categoryName: 'Category', status: 'active', version: 1 };
beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  calls.list.mockResolvedValue({ ok: true, message: 'Page loaded.', items: [product], afterProductId: 'a' });
  calls.index.mockResolvedValue({ ok: true, items: [{ productId: 'a', version: 1, sourceVersion: null, status: 'pending' }], pendingCount: 1 });
});
it('browses authoritative pages and exposes pending or unavailable freshness independently', async () => {
  const select = vi.fn();
  render(<Catalog disabled={false} onSelect={select} onCreated={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Browse catalog / refresh' }));
  fireEvent.click(await screen.findByRole('button', { name: /Authoritative A/ }));
  expect(select).toHaveBeenCalledWith(product);
  expect(await screen.findByText('Search indexing pending')).toBeInTheDocument();
  calls.list.mockResolvedValueOnce({ ok: true, message: 'Page loaded.', items: [{ ...product, productId: 'b', name: 'Authoritative B' }], afterProductId: '' });
  calls.index.mockResolvedValueOnce({ ok: false, items: [], pendingCount: 0 });
  fireEvent.click(screen.getByRole('button', { name: 'Load next catalog page' }));
  expect(await screen.findByRole('button', { name: /Authoritative B/ })).toBeInTheDocument();
  expect(calls.list).toHaveBeenLastCalledWith({ pageSize: 20, afterProductId: 'a' }, { timeoutMs: 35_000 });
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Load next catalog page' })).not.toBeInTheDocument());
  expect(screen.getByRole('button', { name: /Authoritative A/ })).toBeInTheDocument();
  expect(screen.getByText('Indexing not verified')).toBeInTheDocument();
});
it('retains uncertain creation across remount and retries the same payload and operation', async () => {
  const created = vi.fn();
  calls.create.mockResolvedValueOnce({ ok: false, outcome: 'unknown', message: 'Unknown outcome.' });
  const view = render(<Catalog disabled={false} onSelect={vi.fn()} onCreated={created} />);
  fireEvent.click(screen.getByText('Create a product'));
  for (const [name, value] of [['New product ID', 'new'], ['New product name', 'New'], ['New product category', 'Category'], ['New product description', 'Description'], ['Creation reason', 'New item']]) {
    fireEvent.change(screen.getByRole('textbox', { name }), { target: { value } });
  }
  fireEvent.submit(screen.getByRole('textbox', { name: 'New product ID' }).closest('form')!);
  expect(await screen.findByText('Unknown outcome.')).toBeInTheDocument();
  const first = calls.create.mock.calls[0][0];
  expect(first.payload.operationId).toMatch(/^[0-9a-f-]{36}$/);
  expect(first.payload.priceMinor).toBeUndefined();
  view.unmount();
  render(<Catalog disabled={false} onSelect={vi.fn()} onCreated={created} />);
  calls.create.mockResolvedValueOnce({ ok: true, outcome: 'applied', message: 'Created; indexing pending.' });
  fireEvent.click(screen.getByText('Create a product'));
  fireEvent.click(screen.getByRole('button', { name: 'Retry pending creation' }));
  await waitFor(() => expect(created).toHaveBeenCalledWith('new'));
  expect(calls.create.mock.calls[1][0]).toEqual(first);
  expect(sessionStorage.getItem('pim-pending-create')).toBeNull();
});
