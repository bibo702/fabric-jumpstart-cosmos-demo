//-----------------------------------------------------------------------
// <copyright company="Microsoft Corporation">
//        Copyright (c) Microsoft Corporation.  All rights reserved.
//        Licensed under the MIT license. See LICENSE file in the project root for full license information.
// </copyright>
//-----------------------------------------------------------------------

import { useState } from 'react';
import { Archive, Boxes, Cable, CircleAlert, Database, Moon, Sun } from 'lucide-react';
import { useAppTheme } from './hooks/use-theme';

function App() {
  const [view, setView] = useState<'catalog' | 'connection'>('catalog');
  const [status, setStatus] = useState<'active' | 'archived'>('active');
  const { isDark, toggleTheme } = useAppTheme();

  return (
    <div className="min-h-full bg-background font-base text-foreground">
      <header className="flex flex-wrap items-center justify-between gap-400 border-b border-border bg-card px-600 py-400">
        <div className="flex items-center gap-300">
          <Boxes className="icon-size-500 text-primary" aria-hidden="true" />
          <div>
            <p className="font-heading text-400 font-semibold">Product PIM</p>
            <p className="text-200 text-muted-foreground">Rayfin development</p>
          </div>
        </div>
        <button type="button" onClick={toggleTheme} title={isDark ? 'Use light theme' : 'Use dark theme'} aria-label={isDark ? 'Use light theme' : 'Use dark theme'} className="rounded-md border border-border p-200 hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
          {isDark ? <Sun className="icon-size-300" /> : <Moon className="icon-size-300" />}
        </button>
      </header>
      <div className="mx-auto max-w-screen-xl px-400 md:px-800">
        <nav aria-label="Workspace" className="flex gap-200 border-b border-border py-400">
          <button type="button" aria-current={view === 'catalog' ? 'page' : undefined} onClick={() => setView('catalog')} className={`flex items-center gap-300 rounded-md px-300 py-300 text-300 focus-visible:outline-2 focus-visible:outline-ring ${view === 'catalog' ? 'bg-accent font-semibold text-primary' : 'hover:bg-accent'}`}>
            <Boxes className="icon-size-300" aria-hidden="true" />Catalog
          </button>
          <button type="button" aria-current={view === 'connection' ? 'page' : undefined} onClick={() => setView('connection')} className={`flex items-center gap-300 rounded-md px-300 py-300 text-300 focus-visible:outline-2 focus-visible:outline-ring ${view === 'connection' ? 'bg-accent font-semibold text-primary' : 'hover:bg-accent'}`}>
            <Cable className="icon-size-300" aria-hidden="true" />Connection
          </button>
        </nav>
        <main className="min-w-0 py-600">
          <h1 className="font-heading text-600 font-semibold">{view === 'catalog' ? 'Product catalog' : 'Backend connection'}</h1>
          {view === 'catalog' ? (
            <>
              <div role="group" aria-label="Product status" className="mt-600 flex gap-100 border-b border-border pb-400">
                <button type="button" aria-pressed={status === 'active'} onClick={() => setStatus('active')} className={`rounded-md px-400 py-200 text-300 focus-visible:outline-2 focus-visible:outline-ring ${status === 'active' ? 'bg-muted font-semibold' : ''}`}>Active</button>
                <button type="button" aria-pressed={status === 'archived'} onClick={() => setStatus('archived')} className={`flex items-center gap-200 rounded-md px-400 py-200 text-300 focus-visible:outline-2 focus-visible:outline-ring ${status === 'archived' ? 'bg-muted font-semibold' : ''}`}><Archive className="icon-size-200" aria-hidden="true" />Archived</button>
              </div>
              <section aria-label={status === 'active' ? 'Active products' : 'Archived products'} className="grid content-center justify-items-center gap-300 border-b border-border py-800 text-center">
                <Database className="icon-size-700 text-muted-foreground" aria-hidden="true" />
                <h2 className="text-500 font-semibold">Catalog unavailable</h2>
                <p role="status" className="max-w-prose text-300 text-muted-foreground">The isolated PIM backend is not connected.</p>
                <button type="button" onClick={() => setView('connection')} className="mt-200 flex items-center gap-200 rounded-md bg-primary px-400 py-300 text-300 font-semibold text-primary-foreground hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"><Cable className="icon-size-200" aria-hidden="true" />Connection status</button>
              </section>
            </>
          ) : (
            <section aria-label="Connection status" className="mt-600">
              <div role="status" className="flex items-start gap-300 border-y border-border bg-muted px-400 py-400">
                <CircleAlert className="icon-size-300 shrink-0 text-primary" aria-hidden="true" />
                <p className="text-300">Awaiting a separate Rayfin development deployment.</p>
              </div>
              <dl className="mt-400 divide-y divide-border text-300">
                {[
                  ['Catalog backend', 'Not configured'],
                  ['Delegated caller identity', 'Not verified'],
                  ['Read access', 'Not verified'],
                  ['Write access', 'Disabled'],
                ].map(([label, value]) => (
                  <div key={label} className="grid gap-200 py-400 sm:grid-cols-2"><dt className="text-muted-foreground">{label}</dt><dd className="font-medium">{value}</dd></div>
                ))}
              </dl>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
