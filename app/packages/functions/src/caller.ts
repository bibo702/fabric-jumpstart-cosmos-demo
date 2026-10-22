import { createLocalJWKSet, jwtVerify, type JSONWebKeySet } from 'jose';
import { getConfig } from './config.js';

async function fetchSigningKeys(): Promise<JSONWebKeySet> {
  const response = await fetch('https://login.microsoftonline.com/common/discovery/keys', {
    signal: AbortSignal.timeout(10_000),
    redirect: 'error',
  });
  if (!response.ok) throw new Error('Signing keys unavailable');
  const result: unknown = await response.json();
  if (!result || typeof result !== 'object' || !('keys' in result)
    || !Array.isArray(result.keys) || !result.keys.every((key: unknown) =>
      key && typeof key === 'object' && 'kty' in key && typeof key.kty === 'string')) {
    throw new Error('Invalid signing keys');
  }
  return { keys: result.keys };
}

export async function authorizeCaller(
  token: string,
  publishableKey: string,
  loadKeys: (key: string) => Promise<JSONWebKeySet> = fetchSigningKeys,
): Promise<boolean> {
  if (!token || token.length > 16_384) {
    console.warn('Caller verification: missing or oversized token');
    return false;
  }
  try {
    const policy = getConfig().policy;
    const keys = await loadKeys(publishableKey);
    const { payload } = await jwtVerify(token, createLocalJWKSet(keys), {
      algorithms: ['RS256'],
      issuer: policy.issuer,
      audience: policy.audience,
      subject: policy.subject,
      requiredClaims: ['exp', 'nbf', 'tid'],
    });
    return payload.tid === policy.tenant;
  } catch (error) {
    const code = error instanceof Error && 'code' in error && typeof error.code === 'string'
      ? error.code : 'VERIFICATION_UNAVAILABLE';
    console.warn('Caller verification:', code);
    return false;
  }
}