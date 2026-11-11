import test from 'node:test';
import assert from 'node:assert/strict';
import { isTrustedLocalBrowser } from '../pc/local.mjs';

const req = (headers = {}, remoteAddress = '127.0.0.1') => ({ socket: { remoteAddress }, headers: { host: 'localhost:8787', ...headers } });

test('the dashboard opened on the collector PC is trusted without a token', () => {
  assert.equal(isTrustedLocalBrowser(req(), 8787), true);
  assert.equal(isTrustedLocalBrowser(req({ origin: 'http://localhost:8787', 'sec-fetch-site': 'same-origin' }), 8787), true);
  assert.equal(isTrustedLocalBrowser(req({ host: '127.0.0.1:8787' }, '::1'), 8787), true);
});

test('network, tunnel, other websites and DNS rebinding are not trusted', () => {
  assert.equal(isTrustedLocalBrowser(req({}, '192.168.1.20'), 8787), false, 'LAN client');
  assert.equal(isTrustedLocalBrowser(req({ 'cf-connecting-ip': '203.0.113.9' }), 8787), false, 'arrived through the Cloudflare tunnel');
  assert.equal(isTrustedLocalBrowser(req({ 'x-forwarded-for': '203.0.113.9' }), 8787), false, 'proxied');
  assert.equal(isTrustedLocalBrowser(req({ origin: 'https://evil.example' }), 8787), false, 'another website');
  assert.equal(isTrustedLocalBrowser(req({ 'sec-fetch-site': 'cross-site' }), 8787), false, 'cross-site embed');
  assert.equal(isTrustedLocalBrowser(req({ host: 'evil.example:8787' }), 8787), false, 'DNS rebinding');
  assert.equal(isTrustedLocalBrowser(req({ host: 'localhost:9999' }), 8787), false, 'wrong port');
  assert.equal(isTrustedLocalBrowser({ headers: { host: 'localhost:8787' } }, 8787), false, 'no socket');
});
