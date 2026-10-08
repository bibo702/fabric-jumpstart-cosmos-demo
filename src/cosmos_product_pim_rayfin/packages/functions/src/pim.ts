export interface ProductSummary {
  productId: string;
  name: string;
  description: string;
  categoryName: string;
  status: string;
  version: number;
}

export interface ProductReadResult {
  ok: boolean;
  code: string;
  message: string;
  product: ProductSummary | null;
}

export const PIM_UDF_BASE_URL = 'https://api.fabric.microsoft.com/v1/workspaces/d0708f52-ffc4-4d3e-9fab-6e85dd3618fc/userDataFunctions/758636a3-bb2b-4071-bdc8-ba739e611efd/functions';
const PRODUCT_URL = `${PIM_UDF_BASE_URL}/get_product/invoke`;

export function readFailure(code: string, message: string): ProductReadResult {
  return { ok: false, code, message, product: null };
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export async function readBody(response: Response, maxBytes = 65_536): Promise<unknown> {
  if (!response.body) throw new Error('Empty response');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let length = 0;
  let text = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > maxBytes) throw new Error('Response too large');
      text += decoder.decode(value, { stream: true });
    }
    return JSON.parse(text + decoder.decode());
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export async function readProduct(
  productId: string,
  ownerToken: string,
  request: typeof fetch = fetch,
): Promise<ProductReadResult> {
  if (typeof productId !== 'string' || !/^[a-zA-Z0-9_-]{1,100}$/.test(productId)) {
    return readFailure('INVALID_PRODUCT_ID', 'Enter a product ID using letters, numbers, hyphens, or underscores (maximum 100 characters).');
  }
  if (!ownerToken) return readFailure('OWNER_TOKEN_UNAVAILABLE', 'The app owner connection is unavailable.');
  try {
    const response = await request(PRODUCT_URL, {
      method: 'POST',
      headers: {
        Authorization: ['Bearer', ownerToken].join(' '),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ productId }),
      signal: AbortSignal.timeout(20_000),
      redirect: 'error',
    });
    if (!response.ok) {
      await response.body?.cancel();
      return readFailure('BACKEND_UNAVAILABLE', 'PIMv2 rejected the read request. Check the existing UDF runtime and app-owner permissions.');
    }
    const envelope = await readBody(response);
    if (!isRecord(envelope) || envelope.status !== 'Succeeded'
      || envelope.functionName !== 'get_product' || !Array.isArray(envelope.errors)
      || envelope.errors.length !== 0 || !isRecord(envelope.output)) {
      return readFailure('BACKEND_UNAVAILABLE', 'PIMv2 did not return a successful product read.');
    }
    const product = envelope.output;
    if (product.status === 'rejected' && product.code === 'not_found') {
      return readFailure('NOT_FOUND', 'No product was found for this ID.');
    }
    if (product.status === 'rejected' || product.status === 'failed') {
      return readFailure('READ_REJECTED', 'The existing PIMv2 backend rejected this read.');
    }
    if (product.productId !== productId || typeof product.name !== 'string' || product.name.length > 200
      || typeof product.description !== 'string' || product.description.length > 10_000
      || typeof product.categoryName !== 'string' || product.categoryName.length > 200
      || (product.status !== 'active' && product.status !== 'deleted')
      || typeof product.version !== 'number' || !Number.isSafeInteger(product.version) || product.version < 1) {
      return readFailure('INVALID_RESPONSE', 'PIMv2 returned an unexpected product format.');
    }
    return {
      ok: true, code: 'OK', message: 'Product loaded.',
      product: {
        productId, name: product.name, description: product.description,
        categoryName: product.categoryName, status: product.status, version: product.version,
      },
    };
  } catch (error) {
    return error instanceof Error && (error.name === 'TimeoutError' || error.name === 'AbortError')
      ? readFailure('READ_TIMEOUT', 'The product read timed out. Try again.')
      : readFailure('BACKEND_UNAVAILABLE', 'The existing PIMv2 backend could not be read. Try again or check its runtime.');
  }
}
