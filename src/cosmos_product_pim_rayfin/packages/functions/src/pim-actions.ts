import { readBody } from './pim.js';

export interface MutationInput {
  productId: string;
  expectedVersion: number;
  operationId: string;
  reason: string;
  changes: { name?: string; description?: string; categoryName?: string; status?: string };
}

export interface MutationResult {
  ok: boolean;
  outcome: 'applied' | 'rejected' | 'unknown';
  code: string;
  message: string;
  version: number;
  replayed: boolean;
}

export interface HistoryEvent {
  id: string;
  action: string;
  occurredAt: string;
  fromVersion: number;
  toVersion: number;
  actor: { oid: string; tenantId: string; username: string };
  reason: string;
  operationId: string;
  changes: { path: string; oldValue: string | null; newValue: string | null }[];
}

export interface HistoryResult {
  ok: boolean;
  message: string;
  items: HistoryEvent[];
  continuationToken: string;
}

const BASE_URL = 'https://api.fabric.microsoft.com/v1/workspaces/d0708f52-ffc4-4d3e-9fab-6e85dd3618fc/userDataFunctions/758636a3-bb2b-4071-bdc8-ba739e611efd/functions';
const productIdPattern = /^[a-zA-Z0-9_-]{1,100}$/;
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const textLimits: Record<string, number> = { name: 200, description: 10_000, categoryName: 200 };
const rejectionMessages: Record<string, string> = {
  version_conflict: 'This product changed. Reload it and review your changes before saving again.',
  operation_conflict: 'This operation ID was already used for a different change. Reload the product.',
  no_changes: 'No values changed.',
  deleted_product: 'Restore this product before editing its content.',
  forbidden: 'PIMv2 did not grant write access to the app owner.',
  not_found: 'The product no longer exists.',
  invalid_request: 'PIMv2 rejected the change. Check the fields and reason.',
};

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function text(value: unknown, limit: number): value is string {
  return typeof value === 'string' && value.length <= limit;
}

export function mutationFailure(code: string, message: string, uncertain = false): MutationResult {
  return { ok: false, outcome: uncertain ? 'unknown' : 'rejected', code, message, version: 0, replayed: false };
}

async function invoke(action: 'update_product' | 'get_history', body: object, token: string, request: typeof fetch): Promise<Record<string, unknown>> {
  const response = await request(`${BASE_URL}/${action}/invoke`, {
    method: 'POST',
    headers: {
      Authorization: ['Bearer', token].join(' '),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body), signal: AbortSignal.timeout(25_000), redirect: 'error',
  });
  if (!response.ok) {
    await response.body?.cancel();
    throw new Error('Backend unavailable');
  }
  const envelope = await readBody(response, action === 'get_history' ? 1_048_576 : 65_536);
  if (!record(envelope) || envelope.functionName !== action || envelope.status !== 'Succeeded'
    || !Array.isArray(envelope.errors) || envelope.errors.length || !record(envelope.output)) {
    throw new Error('Invalid backend envelope');
  }
  return envelope.output;
}

export async function updateProduct(input: MutationInput, token: string, request: typeof fetch = fetch): Promise<MutationResult> {
  if (!record(input) || !text(input.productId, 100) || !productIdPattern.test(input.productId)
    || !Number.isSafeInteger(input.expectedVersion) || input.expectedVersion < 1
    || !text(input.operationId, 36) || !uuidPattern.test(input.operationId)
    || !text(input.reason, 500) || !input.reason.trim() || !record(input.changes)) {
    return mutationFailure('INVALID_REQUEST', 'A valid product, version, operation ID, and change reason are required.');
  }
  const changes = Object.entries(input.changes);
  if (!changes.length || changes.some(([field, value]) => field === 'status'
    ? value !== 'active' && value !== 'deleted'
    : !Object.hasOwn(textLimits, field) || !text(value, textLimits[field]) || !value.trim())
    || ('status' in input.changes && changes.length !== 1)) {
    return mutationFailure('INVALID_REQUEST', 'Edit product details or change status separately.');
  }
  if (!token) return mutationFailure('OWNER_TOKEN_UNAVAILABLE', 'The app owner connection is unavailable.');
  try {
    const output = await invoke('update_product', { payload: {
      productId: input.productId, expectedVersion: input.expectedVersion,
      operationId: input.operationId, reason: input.reason, changes: input.changes,
    } }, token, request);
    if (output.status === 'rejected') {
      const code = typeof output.code === 'string' && Object.hasOwn(rejectionMessages, output.code) ? output.code : 'REJECTED';
      return mutationFailure(code, rejectionMessages[code] ?? 'PIMv2 rejected this change. Reload the product.');
    }
    if (output.status !== 'applied' || output.productId !== input.productId
      || output.version !== input.expectedVersion + 1 || output.eventId !== `event:${input.operationId.toLowerCase()}`
      || typeof output.replayed !== 'boolean') throw new Error('Unconfirmed mutation');
    return { ok: true, outcome: 'applied', code: 'OK', message: output.replayed ? 'Previously saved change confirmed.' : 'Change saved.', version: output.version, replayed: output.replayed };
  } catch {
    return mutationFailure('OUTCOME_UNKNOWN', 'Save outcome is unknown. Retry the same operation to confirm it; do not submit a new change.', true);
  }
}

export async function readHistory(productId: string, continuationToken: string, token: string, request: typeof fetch = fetch): Promise<HistoryResult> {
  const failure: HistoryResult = { ok: false, message: 'History unavailable. Retry or check the PIMv2 connection.', items: [], continuationToken: '' };
  if (!text(productId, 100) || !productIdPattern.test(productId) || !text(continuationToken, 16_000) || !token) return failure;
  try {
    const output = await invoke('get_history', { productId, pageSize: 20, continuationToken }, token, request);
    if (!Array.isArray(output.items) || output.items.length > 20 || !text(output.continuationToken, 16_000)) return failure;
    const items: HistoryEvent[] = [];
    for (const item of output.items) {
      if (!record(item) || item.productId !== productId || item.docType !== 'auditEvent'
        || !text(item.id, 200) || !text(item.action, 100) || !text(item.occurredAt, 100)
        || !Number.isFinite(Date.parse(item.occurredAt)) || !Number.isSafeInteger(item.fromVersion)
        || !Number.isSafeInteger(item.toVersion) || typeof item.fromVersion !== 'number' || typeof item.toVersion !== 'number'
        || !record(item.actor) || !text(item.actor.oid, 100) || !text(item.actor.tenantId, 100)
        || !text(item.reason, 500) || !text(item.operationId, 100) || !Array.isArray(item.changes) || item.changes.length > 10) return failure;
      const differences: HistoryEvent['changes'] = [];
      for (const difference of item.changes) {
        if (record(difference) && difference.path === '/' && difference.oldValue === null
          && record(difference.newValue) && difference.newValue.productId === productId) {
          for (const field of ['name', 'description', 'categoryName', 'status']) {
            const value = difference.newValue[field];
            if (!text(value, textLimits[field] ?? 100)) return failure;
            differences.push({ path: `/${field}`, oldValue: null, newValue: value });
          }
          continue;
        }
        if (!record(difference) || !text(difference.path, 100)
          || !(difference.oldValue === null || text(difference.oldValue, 10_000))
          || !(difference.newValue === null || text(difference.newValue, 10_000))) return failure;
        differences.push({ path: difference.path, oldValue: difference.oldValue, newValue: difference.newValue });
      }
      items.push({ id: item.id, action: item.action, occurredAt: item.occurredAt,
        fromVersion: item.fromVersion, toVersion: item.toVersion,
        actor: { oid: item.actor.oid, tenantId: item.actor.tenantId, username: text(item.actor.username, 320) ? item.actor.username : '' },
        reason: item.reason, operationId: item.operationId, changes: differences });
    }
    return { ok: true, message: 'History loaded.', items, continuationToken: output.continuationToken };
  } catch { return failure; }
}
