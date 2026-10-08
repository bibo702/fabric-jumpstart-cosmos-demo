//-----------------------------------------------------------------------
// <copyright company="Microsoft Corporation">
//        Copyright (c) Microsoft Corporation.  All rights reserved.
//        Licensed under the MIT license. See LICENSE file in the project root for full license information.
// </copyright>
//-----------------------------------------------------------------------

import { useState } from 'react';
import {
  ArrowRight,
  Boxes,
  Braces,
  Cable,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Database,
  Info,
  Layers3,
  Moon,
  Route,
  Search,
  ShieldCheck,
  Sparkles,
  Sun,
} from 'lucide-react';
import type { AppFunctionsSchema } from '@rayfin-app/functions/types';
import { useAppTheme } from './hooks/use-theme';
import { getRayfinClient } from './lib/rayfin-client';
import { ProductWorkspace } from './ProductWorkspace';

type Product = NonNullable<AppFunctionsSchema['getProduct']['output']['product']>;
type SearchOutput = AppFunctionsSchema['searchCatalog']['output'];
type View = 'catalog' | 'connection';

const PRESETS = [
  {
    id: 'lightweight-shelter',
    label: 'Lightweight shelter',
    prompt: 'lightweight shelter for two campers',
    detail: 'Semantic intent should favor the two-person tent.',
  },
  {
    id: 'cycling-safety',
    label: 'Cycling safety',
    prompt: 'protective safety gear for cycling',
    detail: 'Keyword and semantic signals should favor the helmet.',
  },
  {
    id: 'trail-riding',
    label: 'Trail riding',
    prompt: 'bicycle for riding on outdoor trails',
    detail: 'Semantic similarity should favor the trail bike.',
  },
] as const;

type PresetId = (typeof PRESETS)[number]['id'];

const PIPELINE = [
  {
    icon: Sparkles,
    title: 'Fabric embedding',
    description: 'The notebook uses ai.embed once and stores this named demo vector.',
  },
  {
    icon: ShieldCheck,
    title: 'Governed UDF',
    description: 'Rayfin verifies the signed account; the PIM backend enforces read grants.',
  },
  {
    icon: Layers3,
    title: 'Cosmos indexes',
    description: 'DiskANN evaluates meaning while BM25 evaluates matching terms.',
  },
  {
    icon: Route,
    title: 'RRF ranking',
    description: 'Cosmos fuses both rankings, then products are read from the source of truth.',
  },
] as const;

function App() {
  const [view, setView] = useState<View>('catalog');
  const [productId, setProductId] = useState('');
  const [result, setResult] = useState<AppFunctionsSchema['getProduct']['output'] | null>(null);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState('');
  const [connection, setConnection] = useState<AppFunctionsSchema['getConnectionStatus']['output'] | null>(null);
  const [checking, setChecking] = useState(false);
  const [connectionError, setConnectionError] = useState('');
  const [productBusy, setProductBusy] = useState(false);
  const [queryId, setQueryId] = useState<PresetId>(PRESETS[0].id);
  const [statusFilter, setStatusFilter] = useState('active');
  const [searchResult, setSearchResult] = useState<SearchOutput | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const { isDark, toggleTheme } = useAppTheme();

  const selectedPreset = PRESETS.find((preset) => preset.id === queryId) ?? PRESETS[0];

  async function lookupProduct(selectedId = productId) {
    if (reading || productBusy) return;
    setReading(true);
    setResult(null);
    setReadError('');
    try {
      const client = await getRayfinClient();
      setResult(await client.functions.getProduct.invoke(
        { productId: selectedId.trim() },
        { timeoutMs: 35_000 },
      ));
    } catch {
      setReadError('Product read unavailable. Check the Rayfin connection and try again.');
    } finally {
      setReading(false);
    }
  }

  async function runSearch() {
    if (searching || productBusy) return;
    setSearching(true);
    setSearchResult(null);
    setSearchError('');
    try {
      const client = await getRayfinClient();
      const response = await client.functions.searchCatalog.invoke(
        { queryId, status: statusFilter },
        { timeoutMs: 45_000 },
      );
      setSearchResult(response);
    } catch {
      setSearchError('Hybrid search is unavailable. Check the Rayfin and PIM connections, then retry.');
    } finally {
      setSearching(false);
    }
  }

  async function checkConnection() {
    if (checking) return;
    setChecking(true);
    setConnection(null);
    setConnectionError('');
    try {
      const client = await getRayfinClient();
      setConnection(await client.functions.getConnectionStatus.invoke(
        undefined,
        { timeoutMs: 20_000 },
      ));
    } catch {
      setConnectionError('Rayfin account verification is unavailable. Try signing in again.');
    } finally {
      setChecking(false);
    }
  }

  function selectRankedProduct(product: Product) {
    setProductId(product.productId);
    void lookupProduct(product.productId);
  }

  function updateProduct(product: Product) {
    setResult({ ok: true, code: 'OK', message: 'Product loaded.', product });
    setSearchResult((previous) => previous
      ? {
        ...previous,
        items: previous.items.map((item) => (
          item.productId === product.productId ? { ...item, ...product } : item
        )),
      }
      : previous);
  }

  return (
    <div className="min-h-full bg-[var(--cp-bg)] font-base text-foreground">
      <header className="border-b border-border bg-background">
        <div className="mx-auto flex max-w-screen-xl flex-wrap items-center justify-between gap-400 px-400 py-400 md:px-800">
          <div className="flex items-center gap-300">
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Boxes className="icon-size-400" aria-hidden="true" />
            </span>
            <div>
              <p className="font-heading text-400 font-semibold">Product PIM discovery</p>
              <p className="text-200 text-muted-foreground">Rayfin + Cosmos DB in Microsoft Fabric</p>
            </div>
          </div>
          <div className="flex items-center gap-200">
            <span className="hidden items-center gap-200 rounded-full border border-border px-300 py-200 text-200 text-muted-foreground sm:flex">
              <span className="size-2 rounded-full bg-[var(--cp-success)]" />
              Native hybrid search
            </span>
            <button
              type="button"
              onClick={toggleTheme}
              title={isDark ? 'Use light theme' : 'Use dark theme'}
              aria-label={isDark ? 'Use light theme' : 'Use dark theme'}
              className="rounded-xl border border-border p-200 transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
            >
              {isDark ? <Sun className="icon-size-300" /> : <Moon className="icon-size-300" />}
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-screen-xl px-400 md:px-800">
        <nav aria-label="Workspace" className="flex gap-200 border-b border-border py-300">
          <button
            type="button"
            disabled={productBusy}
            aria-current={view === 'catalog' ? 'page' : undefined}
            onClick={() => setView('catalog')}
            className={`flex items-center gap-200 rounded-xl px-300 py-200 text-300 transition-colors focus-visible:outline-2 focus-visible:outline-ring ${view === 'catalog' ? 'bg-accent font-semibold text-primary' : 'hover:bg-accent'}`}
          >
            <Search className="icon-size-200" aria-hidden="true" />
            Discovery demo
          </button>
          <button
            type="button"
            disabled={productBusy}
            aria-current={view === 'connection' ? 'page' : undefined}
            onClick={() => setView('connection')}
            className={`flex items-center gap-200 rounded-xl px-300 py-200 text-300 transition-colors focus-visible:outline-2 focus-visible:outline-ring ${view === 'connection' ? 'bg-accent font-semibold text-primary' : 'hover:bg-accent'}`}
          >
            <Cable className="icon-size-200" aria-hidden="true" />
            Connection
          </button>
        </nav>

        <main className="min-w-0 py-600">
          {view === 'catalog' ? (
            <>
              <section className="grid gap-500 lg:grid-cols-[minmax(0,1.45fr)_minmax(18rem,0.55fr)] lg:items-end">
                <div>
                  <div className="mb-300 flex items-center gap-200 text-200 font-semibold uppercase tracking-wider text-primary">
                    <Sparkles className="icon-size-200" aria-hidden="true" />
                    Fabric-native relevance
                  </div>
                  <h1 className="max-w-3xl font-heading text-hero-800 font-semibold leading-hero-800">
                    Product catalog
                  </h1>
                  <p className="mt-300 max-w-3xl text-400 leading-600 text-muted-foreground">
                    Explore how Cosmos DB in Fabric combines semantic similarity and
                    full-text relevance, then returns governed product records through Rayfin.
                  </p>
                </div>
                <aside className="rounded-2xl border border-border bg-background p-400">
                  <div className="flex items-start gap-300">
                    <Info className="icon-size-300 shrink-0 text-primary" aria-hidden="true" />
                    <div>
                      <h2 className="text-300 font-semibold">Why named demo searches?</h2>
                      <p className="mt-100 text-200 leading-400 text-muted-foreground">
                        Fabric <code className="font-monospace">ai.embed</code> runs in the
                        acceptance notebook. Rayfin reuses those stored vectors, keeping this
                        demo Fabric-only with no external model endpoint.
                      </p>
                    </div>
                  </div>
                </aside>
              </section>

              <ol aria-label="Hybrid search pipeline" className="mt-600 grid gap-300 md:grid-cols-2 xl:grid-cols-4">
                {PIPELINE.map((step, index) => {
                  const Icon = step.icon;
                  return (
                    <li key={step.title} className="relative rounded-2xl border border-border bg-background p-400">
                      <div className="flex items-center justify-between">
                        <span className="grid size-9 place-items-center rounded-xl bg-accent text-primary">
                          <Icon className="icon-size-300" aria-hidden="true" />
                        </span>
                        <span className="font-numeric text-200 text-muted-foreground">0{index + 1}</span>
                      </div>
                      <h3 className="mt-300 text-300 font-semibold">{step.title}</h3>
                      <p className="mt-100 text-200 leading-400 text-muted-foreground">{step.description}</p>
                    </li>
                  );
                })}
              </ol>

              <section aria-labelledby="hybrid-search-title" className="mt-600 grid gap-500 lg:grid-cols-[minmax(0,1fr)_20rem]">
                <div className="rounded-2xl border border-border bg-background p-400 md:p-600">
                  <div className="flex flex-wrap items-start justify-between gap-300">
                    <div>
                      <h2 id="hybrid-search-title" className="font-heading text-500 font-semibold">
                        Try hybrid discovery
                      </h2>
                      <p className="mt-100 text-300 text-muted-foreground">
                        Select a Fabric-embedded intent and inspect Cosmos ranking.
                      </p>
                    </div>
                    <span className="rounded-full bg-accent px-300 py-200 text-200 font-semibold text-primary">
                      DiskANN + BM25 + RRF
                    </span>
                  </div>

                  <fieldset className="mt-500">
                    <legend className="text-200 font-semibold uppercase tracking-wider text-muted-foreground">
                      Search intent
                    </legend>
                    <div className="mt-300 grid gap-300 md:grid-cols-3">
                      {PRESETS.map((preset) => (
                        <button
                          key={preset.id}
                          type="button"
                          aria-pressed={queryId === preset.id}
                          onClick={() => {
                            setQueryId(preset.id);
                            setSearchResult(null);
                            setSearchError('');
                          }}
                          className={`rounded-2xl border p-300 text-left transition-all motion-reduce:transition-none ${queryId === preset.id ? 'border-primary bg-accent' : 'border-border hover:border-[var(--cp-border-strong)] hover:bg-muted'}`}
                        >
                          <span className="block text-300 font-semibold">{preset.label}</span>
                          <span className="mt-100 block text-200 leading-400 text-muted-foreground">
                            “{preset.prompt}”
                          </span>
                        </button>
                      ))}
                    </div>
                  </fieldset>

                  <div className="mt-400 flex flex-wrap items-end gap-300">
                    <label className="grid min-w-48 flex-1 gap-200 text-200 font-medium">
                      Product status
                      <select
                        value={statusFilter}
                        onChange={(event) => {
                          setStatusFilter(event.target.value);
                          setSearchResult(null);
                        }}
                        className="rounded-xl border border-input bg-background px-300 py-300 text-300 focus-visible:outline-2 focus-visible:outline-ring"
                      >
                        <option value="active">Active products</option>
                        <option value="all">All products</option>
                        <option value="deleted">Archived products</option>
                      </select>
                    </label>
                    <button
                      type="button"
                      onClick={() => void runSearch()}
                      disabled={searching || productBusy}
                      className="flex min-h-11 items-center justify-center gap-200 rounded-xl bg-primary px-500 py-300 text-300 font-semibold text-primary-foreground transition-colors hover:bg-[var(--cp-accent-hover)] disabled:opacity-50"
                    >
                      <Search className="icon-size-200" aria-hidden="true" />
                      {searching ? 'Ranking in Cosmos...' : 'Run hybrid search'}
                    </button>
                  </div>

                  <div role="status" aria-live="polite" className="mt-400 min-h-6 text-300 text-muted-foreground">
                    {searching
                      ? 'Retrieving the stored Fabric embedding and fusing DiskANN with BM25...'
                      : searchError || searchResult?.message || selectedPreset.detail}
                  </div>

                  {searchResult?.ok && (
                    <div className="mt-300 border-t border-border pt-300">
                      <div className="flex flex-wrap gap-200 text-200 text-muted-foreground">
                        <span className="flex items-center gap-100 rounded-full bg-muted px-300 py-200">
                          <Clock3 className="icon-size-100" aria-hidden="true" />
                          {searchResult.elapsedMs} ms bridge time
                        </span>
                        <span className="rounded-full bg-muted px-300 py-200">
                          {searchResult.embeddingDimensions.toLocaleString()} dimensions
                        </span>
                        <span className="rounded-full bg-muted px-300 py-200">
                          {searchResult.items.length} ranked result{searchResult.items.length === 1 ? '' : 's'}
                        </span>
                      </div>
                      <ol className="mt-300 divide-y divide-border">
                        {searchResult.items.map((product) => (
                          <li key={product.productId}>
                            <button
                              type="button"
                              disabled={reading || productBusy}
                              onClick={() => selectRankedProduct(product)}
                              className="group flex w-full items-center gap-300 py-400 text-left transition-colors hover:bg-muted disabled:opacity-50"
                            >
                              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent font-numeric text-300 font-semibold text-primary">
                                {product.rank}
                              </span>
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-300 font-semibold">{product.name}</span>
                                <span className="mt-100 block truncate text-200 text-muted-foreground">
                                  {product.categoryName} · {product.productId} · source v{product.sourceVersion}
                                </span>
                              </span>
                              <ArrowRight className="icon-size-200 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1 motion-reduce:transition-none" aria-hidden="true" />
                            </button>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                </div>

                <aside aria-label="Search execution details" className="rounded-2xl border border-border bg-[var(--cp-bg-elevated)] p-400">
                  <div className="flex items-center gap-200">
                    <Braces className="icon-size-300 text-primary" aria-hidden="true" />
                    <h2 className="text-300 font-semibold">What Cosmos receives</h2>
                  </div>
                  <dl className="mt-400 space-y-400 text-200">
                    <div>
                      <dt className="font-semibold text-muted-foreground">Preset ID</dt>
                      <dd className="mt-100 break-words font-monospace">{selectedPreset.id}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-muted-foreground">Full-text terms</dt>
                      <dd className="mt-200 flex flex-wrap gap-100">
                        {(searchResult?.queryTerms ?? selectedPreset.prompt.split(' ')).map((term) => (
                          <span key={term} className="rounded-md border border-border bg-background px-200 py-100 font-monospace">
                            {term}
                          </span>
                        ))}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-muted-foreground">Vector path</dt>
                      <dd className="mt-100 font-monospace">/embedding · cosine · DiskANN</dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-muted-foreground">Fusion</dt>
                      <dd className="mt-100 font-monospace">{searchResult?.ranking || 'RRF(VectorDistance, FullTextScore)'}</dd>
                    </div>
                  </dl>
                  <div className="mt-500 rounded-xl border border-border bg-background p-300">
                    <div className="flex items-center gap-200 text-200 font-semibold">
                      <CheckCircle2 className="icon-size-200 text-[var(--cp-success)]" aria-hidden="true" />
                      No duplicate catalog
                    </div>
                    <p className="mt-100 text-200 leading-400 text-muted-foreground">
                      Search documents hold derived text and vectors. Product details still come from authoritative <code className="font-monospace">ProductPim</code> records.
                    </p>
                  </div>
                </aside>
              </section>

              <section aria-labelledby="direct-lookup-title" className="mt-600 rounded-2xl border border-border bg-background p-400">
                <div className="flex items-center gap-300">
                  <Database className="icon-size-300 text-primary" aria-hidden="true" />
                  <div>
                    <h2 id="direct-lookup-title" className="text-300 font-semibold">Direct governed lookup</h2>
                    <p className="text-200 text-muted-foreground">Open a known product ID without search ranking.</p>
                  </div>
                </div>
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    void lookupProduct();
                  }}
                  className="mt-300 flex flex-wrap items-end gap-300"
                >
                  <label className="grid min-w-0 flex-1 gap-200 text-200 font-medium">
                    Product ID
                    <input
                      value={productId}
                      onChange={(event) => {
                        setProductId(event.target.value);
                        setResult(null);
                        setReadError('');
                      }}
                      required
                      maxLength={100}
                      pattern="[a-zA-Z0-9_\-]+"
                      disabled={reading || productBusy}
                      autoComplete="off"
                      placeholder="bike-100"
                      className="w-full rounded-xl border border-input bg-background px-300 py-300 text-300 focus-visible:outline-2 focus-visible:outline-ring"
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={reading || productBusy || !productId.trim()}
                    aria-label="Look up product"
                    className="rounded-xl border border-border p-300 text-primary transition-colors hover:bg-accent disabled:opacity-50"
                  >
                    <Search className="icon-size-400" />
                  </button>
                </form>
              </section>

              <p role="status" aria-live="polite" className="py-400 text-300 text-muted-foreground">
                {reading ? 'Reading product...' : readError || result?.message || 'No product selected.'}
              </p>
              {result?.ok && result.product ? (
                <ProductWorkspace
                  key={result.product.productId}
                  product={result.product}
                  onBusyChange={setProductBusy}
                  onUpdated={updateProduct}
                />
              ) : (
                <section aria-label="Product lookup" className="grid content-center justify-items-center gap-300 border-y border-border py-800 text-center">
                  <Database className="icon-size-700 text-muted-foreground" aria-hidden="true" />
                  <h2 className="text-500 font-semibold">
                    {reading ? 'Reading product' : result || readError ? 'Product unavailable' : 'Select a ranked product'}
                  </h2>
                  <p className="max-w-lg text-300 text-muted-foreground">
                    Run a hybrid search above or enter a product ID to open the audited editing workspace.
                  </p>
                </section>
              )}
            </>
          ) : (
            <section aria-labelledby="connection-title" className="mx-auto max-w-3xl">
              <h1 id="connection-title" className="font-heading text-600 font-semibold">Backend connection</h1>
              <p className="mt-200 text-300 text-muted-foreground">
                Verify each security and data boundary used by this demo.
              </p>
              <div role="status" className="mt-500 flex items-start gap-300 rounded-2xl border border-border bg-background px-400 py-400">
                <CircleAlert className="icon-size-300 shrink-0 text-primary" aria-hidden="true" />
                <p className="text-300">
                  {checking
                    ? 'Verifying account...'
                    : connectionError || (connection
                      ? connection.authorized
                        ? 'Account verified. Product and search operations are checked separately.'
                        : 'Access denied for this account.'
                      : 'Account verification not run.')}
                </p>
              </div>
              <dl className="mt-400 divide-y divide-border rounded-2xl border border-border bg-background px-400 text-300">
                {[
                  ['Backend', 'PIMv2_ProductPimBackend'],
                  ['External access identity', 'App owner'],
                  ['Account restriction', connection?.authorized ? 'Verified' : 'Not verified'],
                  ['Product read', result?.ok ? 'Verified' : result?.code || 'Not verified'],
                  ['Hybrid search', searchResult?.ok ? 'Verified with RRF' : connection?.searchEnabled ? 'Enabled; not tested' : 'Not verified'],
                  ['Write bridge', connection?.authorized && connection.writesEnabled ? 'Enabled; PIMv2 enforces permissions' : 'Not checked'],
                ].map(([label, value]) => (
                  <div key={label} className="grid gap-200 py-400 sm:grid-cols-2">
                    <dt className="text-muted-foreground">{label}</dt>
                    <dd className="break-words font-medium">{value}</dd>
                  </div>
                ))}
              </dl>
              <button
                type="button"
                onClick={() => void checkConnection()}
                disabled={checking}
                className="mt-400 flex items-center gap-200 rounded-xl border border-border px-400 py-300 text-300 transition-colors hover:bg-accent disabled:opacity-50"
              >
                <Cable className="icon-size-300" aria-hidden="true" />
                Check account
              </button>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
