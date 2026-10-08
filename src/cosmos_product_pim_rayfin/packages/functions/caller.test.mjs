import assert from 'node:assert/strict';
import { test } from 'node:test';
import { exportJWK, generateKeyPair, SignJWT } from 'jose';
import { authorizeCaller, CALLER_POLICY } from './dist/caller.js';

const { privateKey, publicKey } = await generateKeyPair('RS256');
const keys = { keys: [{ ...await exportJWK(publicKey), kid: 'test-key' }] };
const loadKeys = async () => keys;

function sign(overrides = {}, key = privateKey) {
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({
    iss: CALLER_POLICY.issuer,
    aud: CALLER_POLICY.audience,
    sub: CALLER_POLICY.subject,
    tid: CALLER_POLICY.tenant,
    nbf: now - 10,
    exp: now + 60,
    ...overrides,
  }).setProtectedHeader({ alg: 'RS256', kid: 'test-key' }).sign(key);
}

test('accepts only the signed account and app scoped identity', async () => {
  assert.equal(await authorizeCaller(await sign(), 'public-key', loadKeys), true);
});

for (const [name, claims] of Object.entries({
  'another account': { sub: CALLER_POLICY.subject.replace('bd801010', '00000000') },
  'another app': { sub: CALLER_POLICY.subject.replace('a8571d28', '00000000') },
  'another tenant': { tid: 'another-tenant' },
  'another issuer': { iss: 'https://untrusted.example/' },
  'another audience': { aud: 'another-app' },
  'expired token': { exp: 1 },
  'future token': { nbf: Math.floor(Date.now() / 1000) + 3600 },
  'missing expiry': { exp: undefined },
})) {
  test(`rejects ${name}`, async () => {
    assert.equal(await authorizeCaller(await sign(claims), 'public-key', loadKeys), false);
  });
}

test('rejects a forged signature', async () => {
  const attacker = await generateKeyPair('RS256');
  assert.equal(await authorizeCaller(await sign({}, attacker.privateKey), 'public-key', loadKeys), false);
});

test('rejects absent and oversized tokens before retrieving keys', async () => {
  const unexpected = async () => assert.fail('Key lookup must not run');
  assert.equal(await authorizeCaller('', 'public-key', unexpected), false);
  assert.equal(await authorizeCaller('x'.repeat(16_385), 'public-key', unexpected), false);
});

test('fails closed when signing keys cannot be retrieved', async () => {
  assert.equal(await authorizeCaller(await sign(), 'public-key', async () => {
    throw new Error('Unavailable');
  }), false);
});