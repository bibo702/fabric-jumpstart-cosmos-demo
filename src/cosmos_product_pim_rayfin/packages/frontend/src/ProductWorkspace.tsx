import { useEffect, useState } from 'react';
import { Archive, ArrowRight, Check, Clock3, History, RefreshCw, RotateCcw, Save, UserRound } from 'lucide-react';
import type { AppFunctionsSchema } from '@rayfin-app/functions/types';
import { getRayfinClient } from './lib/rayfin-client';

type Product = NonNullable<AppFunctionsSchema['getProduct']['output']['product']>;
type Mutation = AppFunctionsSchema['saveProduct']['input']['payload'];
type Event = AppFunctionsSchema['getHistory']['output']['items'][number];
const fieldClass = 'w-full rounded-md border border-border bg-background px-300 py-300 text-300 disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-ring';
const buttonClass = 'inline-flex items-center justify-center gap-200 rounded-md border border-border px-400 py-300 text-300 font-semibold hover:bg-accent disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-ring';
const fieldNames: Record<string, string> = { '/name': 'Name', '/description': 'Description', '/categoryName': 'Category', '/status': 'Status' };
const actionNames: Record<string, string> = { ProductCreated: 'Created', ProductUpdated: 'Updated', ProductDeleted: 'Archived', ProductRestored: 'Restored' };

function restorePending(productId: string): Mutation | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(`pim-pending:${productId}`) ?? 'null');
    if (value && typeof value === 'object' && 'productId' in value && value.productId === productId
      && 'expectedVersion' in value && typeof value.expectedVersion === 'number'
      && 'operationId' in value && typeof value.operationId === 'string'
      && 'reason' in value && typeof value.reason === 'string'
      && 'changes' in value && value.changes && typeof value.changes === 'object') {
      const changes: Mutation['changes'] = {};
      for (const field of ['name', 'description', 'categoryName', 'status'] as const) {
        if (field in value.changes) {
          const entry: unknown = Reflect.get(value.changes, field);
          if (typeof entry !== 'string') return null;
          changes[field] = entry;
        }
      }
      return { productId, expectedVersion: value.expectedVersion, operationId: value.operationId, reason: value.reason, changes };
    }
  } catch { return null; }
  return null;
}

export function ProductWorkspace({ product, onUpdated, onBusyChange }: { product: Product; onUpdated: (product: Product) => void; onBusyChange: (busy: boolean) => void }) {
  const [draft, setDraft] = useState({ name: product.name, description: product.description, categoryName: product.categoryName });
  const [reason, setReason] = useState('');
  const [pending, setPending] = useState<Mutation | null>(() => restorePending(product.productId));
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [needsReload, setNeedsReload] = useState(false);
  const [message, setMessage] = useState(pending ? 'An unconfirmed save exists. Retry it to confirm the outcome.' : '');
  const [events, setEvents] = useState<Event[]>([]);
  const [cursor, setCursor] = useState('');
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [confirmStatus, setConfirmStatus] = useState(false);
  const [writeVerified, setWriteVerified] = useState(false);
  const busy = saving || refreshing;
  const locked = busy || pending !== null || needsReload;
  const changed = draft.name.trim() !== product.name || draft.description.trim() !== product.description || draft.categoryName.trim() !== product.categoryName;

  useEffect(() => {
    onBusyChange(busy);
    return () => onBusyChange(false);
  }, [busy, onBusyChange]);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const client = await getRayfinClient();
        const result = await client.functions.getHistory.invoke({ productId: product.productId, continuationToken: '' }, { timeoutMs: 35_000 });
        if (!active) return;
        if (!result.ok) { setHistoryError(result.message); return; }
        setEvents(result.items);
        setCursor(result.continuationToken);
      } catch { if (active) setHistoryError('History unavailable. Try again.'); }
      finally { if (active) setHistoryLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [product.productId, product.version, historyRefresh]);

  function refreshHistory() {
    setEvents([]);
    setCursor('');
    setHistoryError('');
    setHistoryLoading(true);
    setHistoryRefresh((value) => value + 1);
  }

  async function loadMore() {
    if (historyLoading || !cursor) return;
    setHistoryLoading(true);
    setHistoryError('');
    try {
      const client = await getRayfinClient();
      const result = await client.functions.getHistory.invoke({ productId: product.productId, continuationToken: cursor }, { timeoutMs: 35_000 });
      if (!result.ok) { setHistoryError(result.message); return; }
      setEvents((previous) => [...previous, ...result.items.filter((item) => !previous.some((old) => old.id === item.id))]);
      setCursor(result.continuationToken === cursor ? '' : result.continuationToken);
    } catch { setHistoryError('Older history unavailable. Try again.'); }
    finally { setHistoryLoading(false); }
  }

  async function reload() {
    setRefreshing(true);
    try {
      const client = await getRayfinClient();
      const result = await client.functions.getProduct.invoke({ productId: product.productId }, { timeoutMs: 35_000 });
      if (!result.ok || !result.product) { setMessage(result.message); setNeedsReload(true); return; }
      setDraft({ name: result.product.name, description: result.product.description, categoryName: result.product.categoryName });
      onUpdated(result.product);
      setNeedsReload(false);
      refreshHistory();
    } catch { setMessage('Product reload failed. Reload before making another change.'); setNeedsReload(true); }
    finally { setRefreshing(false); }
  }

  async function submit(payload: Mutation) {
    if (busy) return;
    try { sessionStorage.setItem(`pim-pending:${product.productId}`, JSON.stringify(payload)); }
    catch { setMessage('Browser storage is unavailable. Saving is blocked to protect retry safety.'); return; }
    setPending(payload);
    setSaving(true);
    setConfirmStatus(false);
    setMessage('Saving to PIMv2...');
    try {
      const client = await getRayfinClient();
      const result = await client.functions.saveProduct.invoke({ payload }, { timeoutMs: 40_000 });
      setMessage(result.message);
      if (result.outcome === 'unknown') return;
      sessionStorage.removeItem(`pim-pending:${product.productId}`);
      setPending(null);
      if (result.ok) {
        setWriteVerified(true);
        setReason('');
        setNeedsReload(true);
        await reload();
      } else if (['version_conflict', 'operation_conflict', 'deleted_product', 'not_found'].includes(result.code)) {
        setNeedsReload(true);
      }
    } catch { setMessage('Save outcome is unknown. Retry the pending save with its original operation ID.'); }
    finally { setSaving(false); }
  }

  function newChange(status?: string) {
    const changes: Mutation['changes'] = {};
    if (status) changes.status = status;
    else for (const field of ['name', 'description', 'categoryName'] as const) {
      if (draft[field].trim() !== product[field]) changes[field] = draft[field].trim();
    }
    void submit({ productId: product.productId, expectedVersion: product.version, operationId: crypto.randomUUID(), reason: reason.trim(), changes });
  }

  return (
    <section aria-label="Product details" className="min-w-0 border-t border-border">
      <div className="flex flex-wrap items-start justify-between gap-300 py-400">
        <div className="min-w-0">
          <p className="break-all font-mono text-200 text-muted-foreground">{product.productId}</p>
          <h2 className="mt-200 break-words text-500 font-semibold">{product.name}</h2>
          <div className="mt-200 flex flex-wrap items-center gap-300 text-200 text-muted-foreground"><span className="font-semibold text-primary">{product.status === 'deleted' ? 'Archived' : 'Active'}</span><span>Version {product.version}</span>{writeVerified && <span className="inline-flex items-center gap-100"><Check className="icon-size-200" />Write verified</span>}</div>
        </div>
        <button type="button" title="Reload product" aria-label="Reload product" disabled={busy || pending !== null} onClick={() => void reload()} className={buttonClass}><RefreshCw className="icon-size-300" /></button>
      </div>
      <div className="grid min-w-0 gap-800 lg:grid-cols-2">
        <form onSubmit={(event) => { event.preventDefault(); newChange(); }} className="min-w-0 space-y-400">
          <h3 className="text-400 font-semibold">Product details</h3>
          <fieldset disabled={locked || product.status === 'deleted'} className="min-w-0 space-y-400">
            <label className="grid gap-200 text-300">Name<input required maxLength={200} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className={fieldClass} /></label>
            <label className="grid gap-200 text-300">Category<input required maxLength={200} value={draft.categoryName} onChange={(event) => setDraft({ ...draft, categoryName: event.target.value })} className={fieldClass} /></label>
            <label className="grid gap-200 text-300">Description<textarea required maxLength={10_000} rows={6} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} className={fieldClass} /></label>
          </fieldset>
          <label className="grid gap-200 text-300">Reason for change<textarea required maxLength={500} rows={2} value={reason} disabled={locked} onChange={(event) => setReason(event.target.value)} className={fieldClass} /></label>
          <div className="flex flex-wrap gap-300">
            <button type="submit" disabled={locked || product.status === 'deleted' || !changed || !reason.trim()} className={`${buttonClass} bg-primary text-primary-foreground`}><Save className="icon-size-300" />Save changes</button>
            <button type="button" disabled={locked || !reason.trim() || changed} onClick={() => setConfirmStatus(true)} className={buttonClass}>{product.status === 'deleted' ? <RotateCcw className="icon-size-300" /> : <Archive className="icon-size-300" />}{product.status === 'deleted' ? 'Restore product' : 'Archive product'}</button>
          </div>
          {confirmStatus && <div role="alert" className="space-y-300 border-y border-border bg-muted py-400"><p className="text-300">{product.status === 'deleted' ? 'Restore this product to Active?' : 'Archive this product? Its record and history will be preserved.'}</p><div className="flex flex-wrap gap-300"><button type="button" disabled={locked} onClick={() => newChange(product.status === 'deleted' ? 'active' : 'deleted')} className={buttonClass}>Confirm {product.status === 'deleted' ? 'restore' : 'archive'}</button><button type="button" onClick={() => setConfirmStatus(false)} className={buttonClass}>Cancel</button></div></div>}
          {message && <p role="status" className="break-words text-300">{message}</p>}
          {pending && <div className="space-y-300 border-y border-border py-400"><p className="break-all font-mono text-200 text-muted-foreground">Operation {pending.operationId}</p><button type="button" disabled={busy} onClick={() => void submit(pending)} className={buttonClass}><RefreshCw className="icon-size-300" />Retry pending save</button></div>}
          {needsReload && !pending && <p role="alert" className="text-300 text-primary">Reload the product before making another change.</p>}
        </form>
        <section aria-label="Change history" className="min-w-0">
          <div className="flex items-center justify-between gap-300"><h3 className="flex items-center gap-200 text-400 font-semibold"><History className="icon-size-300 text-primary" />Change history</h3><button type="button" title="Refresh history" aria-label="Refresh history" disabled={historyLoading} onClick={refreshHistory} className={buttonClass}><RefreshCw className="icon-size-200" /></button></div>
          {historyError && <p role="alert" className="py-400 text-300 text-primary">{historyError}</p>}
          {historyLoading && <p role="status" className="py-400 text-300 text-muted-foreground">Loading history...</p>}
          {!historyLoading && !historyError && events.length === 0 && <p className="py-400 text-300 text-muted-foreground">No changes recorded.</p>}
          <ol className="mt-400 divide-y divide-border">
            {events.map((entry) => <li key={entry.id} className="min-w-0 border-l-2 border-primary py-400 pl-400">
              <div className="flex flex-wrap items-center justify-between gap-200"><h4 className="text-300 font-semibold">{actionNames[entry.action] ?? entry.action}</h4><span className="flex items-center gap-100 font-mono text-200 text-muted-foreground">v{entry.fromVersion}<ArrowRight className="icon-size-100" />v{entry.toVersion}</span></div>
              <p className="mt-200 flex items-start gap-200 text-200 text-muted-foreground"><Clock3 className="icon-size-200 shrink-0" /><time dateTime={entry.occurredAt}>{new Date(entry.occurredAt).toLocaleString()}</time></p>
              <p className="mt-200 flex items-start gap-200 break-all text-200"><UserRound className="icon-size-200 shrink-0" /><span title={`Object ID: ${entry.actor.oid}; Tenant: ${entry.actor.tenantId}`}>{entry.actor.username || entry.actor.oid}</span></p>
              <p className="my-300 whitespace-pre-wrap break-words text-300">{entry.reason}</p>
              {entry.changes.map((change, index) => <div key={`${change.path}:${index}`} className="mb-300 min-w-0 border-t border-border pt-300">
                <p className="mb-200 break-words text-200 font-semibold">{fieldNames[change.path] ?? change.path}</p>
                <div className="grid min-w-0 gap-300 sm:grid-cols-2"><div className="min-w-0"><p className="text-200 text-muted-foreground">Before</p><p className="whitespace-pre-wrap break-words text-300 text-muted-foreground">{change.oldValue ?? 'Not set'}</p></div><div className="min-w-0"><p className="text-200 text-primary">After</p><p className="whitespace-pre-wrap break-words text-300">{change.newValue ?? 'Not set'}</p></div></div>
              </div>)}
              <details className="mt-300 text-200 text-muted-foreground"><summary className="cursor-pointer">Audit identity</summary><dl className="mt-200 space-y-200 break-all"><div><dt>Object ID</dt><dd className="font-mono">{entry.actor.oid}</dd></div><div><dt>Tenant ID</dt><dd className="font-mono">{entry.actor.tenantId}</dd></div><div><dt>Operation ID</dt><dd className="font-mono">{entry.operationId}</dd></div></dl></details>
            </li>)}
          </ol>
          {cursor && <button type="button" disabled={historyLoading} onClick={() => void loadMore()} className={`${buttonClass} mt-400`}>Load older changes</button>}
        </section>
      </div>
    </section>
  );
}