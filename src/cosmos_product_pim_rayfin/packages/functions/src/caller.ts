import { createLocalJWKSet, jwtVerify, type JSONWebKeySet } from 'jose';

export const CALLER_POLICY = Object.freeze({
  issuer: 'https://sts.windows.net/975f013f-7f24-47e8-a7d3-abc4752bf346/',
  audience: 'ef403b6c-5f3e-40ac-8685-28eed2922ad5',
  tenant: '975f013f-7f24-47e8-a7d3-abc4752bf346',
  subject: '/eid1/c/pub/t/PwFflyR_6Een06vEdSvzRg/a/bDtA7z5frECGhSju0pIq1Q/workspaces/d0708f52-ffc4-4d3e-9fab-6e85dd3618fc/projects/a8571d28-2f7e-41e2-b5dd-e9380f5aa444/users/bd801010-8a65-4c02-ab21-e6586edea69e',
});

export const RAYFIN_ENDPOINT =
  'https://pbipmsitwcus23-msit.pbidedicated.windows.net/webapi/capacities/3eaedfb5-b631-4c7e-8928-6efae55ea523/workloads/BaaS/BaaSService/automatic/v1/workspaces/d0708f52-ffc4-4d3e-9fab-6e85dd3618fc/appbackends/a8571d28-2f7e-41e2-b5dd-e9380f5aa444/';

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
    const keys = await loadKeys(publishableKey);
    const { payload } = await jwtVerify(token, createLocalJWKSet(keys), {
      algorithms: ['RS256'],
      issuer: CALLER_POLICY.issuer,
      audience: CALLER_POLICY.audience,
      subject: CALLER_POLICY.subject,
      requiredClaims: ['exp', 'nbf', 'tid'],
    });
    return payload.tid === CALLER_POLICY.tenant;
  } catch (error) {
    const code = error instanceof Error && 'code' in error && typeof error.code === 'string'
      ? error.code : 'VERIFICATION_UNAVAILABLE';
    console.warn('Caller verification:', code);
    return false;
  }
}