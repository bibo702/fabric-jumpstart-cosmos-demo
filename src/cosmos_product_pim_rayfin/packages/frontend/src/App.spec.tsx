//-----------------------------------------------------------------------
// <copyright company="Microsoft Corporation">
//        Copyright (c) Microsoft Corporation.  All rights reserved.
//        Licensed under the MIT license. See LICENSE file in the project root for full license information.
// </copyright>
//-----------------------------------------------------------------------

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

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
  it('renders without throwing', () => {
    expect(() => render(<App />)).not.toThrow();
  });

  it('mounts content into the document', () => {
    render(<App />);
    expect(document.body).not.toBeEmptyDOMElement();
  });

  it('shows an unavailable backend rather than invented product data', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'Product catalog' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('not connected');
    expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument();
  });

  it('opens connection status and keeps writes disabled', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Connection status' }));
    expect(screen.getByRole('heading', { name: 'Backend connection' })).toBeInTheDocument();
    expect(screen.getByText('Disabled')).toBeInTheDocument();
  });

  it('switches catalog status without implying a successful query', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Archived' }));
    expect(screen.getByRole('button', { name: 'Archived' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('region', { name: 'Archived products' })).toHaveTextContent('Catalog unavailable');
  });
});
