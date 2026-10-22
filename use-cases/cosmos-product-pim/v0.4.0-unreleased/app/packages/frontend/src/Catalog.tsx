import { useState } from 'react';
import type { AppFunctionsSchema } from '@rayfin-app/functions/types';
import { getRayfinClient } from './lib/rayfin-client';

type Product = AppFunctionsSchema['listProducts']['output']['items'][number];
type Creation = AppFunctionsSchema['createProduct']['input']['payload'];
const button = 'rounded-xl border border-border px-400 py-300 text-300 hover:bg-accent disabled:opacity-50';
const field = 'rounded-md border border-border bg-background px-300 py-300 text-300';
const pendingKey = 'pim-pending-create';

function restoreCreation(): Creation | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(pendingKey) ?? 'null');
    if (!value || typeof value !== 'object') return null;
    for (const key of ['productId', 'operationId', 'reason', 'name', 'description', 'categoryName']) {
      if (!(key in value) || typeof Reflect.get(value, key) !== 'string') return null;
    }
    return { productId: Reflect.get(value, 'productId'), operationId: Reflect.get(value, 'operationId'),
      reason: Reflect.get(value, 'reason'), name: Reflect.get(value, 'name'),
      description: Reflect.get(value, 'description'), categoryName: Reflect.get(value, 'categoryName') };
  } catch { return null; }
}

export function Catalog({ onSelect, disabled, onCreated }: { onSelect: (product: Product) => void; disabled: boolean; onCreated: (productId: string) => void }) {
  const [items, setItems] = useState<Product[]>([]);
  const [cursor, setCursor] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [freshness, setFreshness] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<Creation | null>(restoreCreation);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({ productId: '', name: '', categoryName: '', description: '', reason: '' });
  const [createMessage, setCreateMessage] = useState('');

  async function browse(afterProductId = '') {
    if (busy || disabled || creating) return;
    setBusy(true);
    setMessage('Reading the authoritative catalog...');
    try {
      const client = await getRayfinClient();
      const page = await client.functions.listProducts.invoke({ pageSize: 20, afterProductId }, { timeoutMs: 35_000 });
      if (!page.ok) { setMessage(page.message); return; }
      setItems((previous) => afterProductId ? [...previous.filter((item) => !page.items.some((next) => next.productId === item.productId)), ...page.items] : page.items);
      setCursor(page.afterProductId);
      setLoaded(true);
      setMessage(page.items.length ? page.message : 'No products on this catalog page.');
      if (!afterProductId) setFreshness({});
      if (page.items.length) {
        const status = await client.functions.getSearchIndexStatus.invoke({ productIds: page.items.map((item) => item.productId) }, { timeoutMs: 35_000 });
        setFreshness((previous) => ({ ...previous, ...Object.fromEntries(page.items.map((item) => {
          const entry = status.ok ? status.items.find((next) => next.productId === item.productId) : undefined;
          return [item.productId, !entry ? 'Indexing not verified' : entry.status === 'current' && entry.version === item.version ? 'Search current at check' : 'Search indexing pending'];
        })) }));
      }
    } catch { setMessage('Catalog or freshness unavailable. Retry; search is not required for browsing.'); }
    finally { setBusy(false); }
  }

  async function create(payload: Creation) {
    if (creating || disabled || busy) return;
    try { sessionStorage.setItem(pendingKey, JSON.stringify(payload)); }
    catch { setCreateMessage('Browser retry storage unavailable. Creation blocked.'); return; }
    setPending(payload);
    setCreating(true);
    setCreateMessage('Creating product atomically...');
    try {
      const client = await getRayfinClient();
      const result = await client.functions.createProduct.invoke({ payload }, { timeoutMs: 40_000 });
      setCreateMessage(result.message);
      if (result.outcome === 'unknown') return;
      sessionStorage.removeItem(pendingKey);
      setPending(null);
      if (result.ok) {
        setDraft({ productId: '', name: '', categoryName: '', description: '', reason: '' });
        setLoaded(false);
        setItems([]);
        setCursor('');
        setFreshness({});
        onCreated(payload.productId);
      }
    } catch { setCreateMessage('Creation outcome unknown. Retry the original operation; do not create a new one.'); }
    finally { setCreating(false); }
  }

  return <section aria-label="Authoritative catalog" className="mt-600 space-y-400 rounded-2xl border border-border bg-background p-400">
    <h2 className="font-heading text-500 font-semibold">Browse authoritative products</h2>
    <p className="text-300 text-muted-foreground">Catalog paging reads Cosmos product records directly, independently of search or indexing. Pages are not a transactional snapshot.</p>
    <button className={button} disabled={busy || disabled || creating} onClick={() => void browse()}>Browse catalog / refresh</button>
    <p role="status" className="text-300">{message}</p>
    <ul className="divide-y divide-border">{items.map((item) => <li key={item.productId} className="py-300">
      <button disabled={disabled || creating} className={`${button} text-left`} onClick={() => onSelect(item)}>{item.name} · {item.productId} · v{item.version} · {item.status}</button>
      <p className="mt-100 text-200 text-muted-foreground">{freshness[item.productId] ?? 'Indexing not verified'}</p>
    </li>)}</ul>
    {loaded && cursor && <button className={button} disabled={busy || disabled || creating} onClick={() => void browse(cursor)}>Load next catalog page</button>}
    <details>
      <summary className="cursor-pointer text-400 font-semibold">Create a product</summary>
      <p className="my-300 text-300 text-muted-foreground">Creates the product and audit receipt atomically. Initial commercial values: priceMinor 0, currency USD (read-only). Search indexing runs separately.</p>
      <form className="grid gap-300" onSubmit={(event) => { event.preventDefault(); void create({ ...draft, operationId: crypto.randomUUID() }); }}>
        <fieldset disabled={creating || disabled || pending !== null || busy} className="grid gap-300">
          {(['productId', 'name', 'categoryName', 'description', 'reason'] as const).map((key) => <label key={key} className="grid gap-200 text-300">
            {{ productId: 'New product ID', name: 'New product name', categoryName: 'New product category', description: 'New product description', reason: 'Creation reason' }[key]}
            <input className={field} required pattern={key === 'productId' ? '[a-zA-Z0-9_-]+' : undefined} maxLength={key === 'productId' ? 100 : key === 'description' ? 10_000 : key === 'reason' ? 500 : 200} value={draft[key]} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} />
          </label>)}
          <button className={button} type="submit">Create product atomically</button>
        </fieldset>
      </form>
      {pending && <div className="mt-300 space-y-200"><p className="break-all text-200">Unconfirmed creation: {pending.productId} · operation {pending.operationId}. Original payload retained for retry.</p><button className={button} disabled={creating || disabled || busy} onClick={() => void create(pending)}>Retry pending creation</button></div>}
      <p role="status" className="mt-300 text-300">{createMessage || (pending ? 'Resolve the pending creation before submitting another.' : '')}</p>
    </details>
  </section>;
}
