// "This PC's own browser" check. The dashboard opened at http://localhost:<port> on the collector PC
// needs no token. A request qualifies only if ALL of these hold:
//   - it arrives on a loopback socket (not from the network),
//   - the Host header is localhost/127.0.0.1/[::1] on our port (blocks DNS rebinding),
//   - it did not come through a proxy or tunnel (no Cloudflare / forwarding headers),
//   - Origin, if present, is that same local origin (blocks other websites' requests),
//   - Sec-Fetch-Site, if present, is same-origin or none (blocks cross-site embeds such as <img>).
// Phones (through the tunnel or USB) authenticate with their per-session pairing key instead.
const LOOPBACK = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);
const PROXY_HEADERS = ['cf-connecting-ip', 'cf-ray', 'x-forwarded-for', 'x-forwarded-host', 'forwarded'];

export function isTrustedLocalBrowser(req, port) {
  if (!LOOPBACK.has(req.socket?.remoteAddress)) return false;
  const hosts = [`localhost:${port}`, `127.0.0.1:${port}`, `[::1]:${port}`];
  if (!hosts.includes(req.headers.host)) return false;
  if (PROXY_HEADERS.some(name => req.headers[name] !== undefined)) return false;
  const origin = req.headers.origin;
  if (origin && !hosts.map(host => 'http://' + host).includes(origin)) return false;
  const site = req.headers['sec-fetch-site'];
  if (site && site !== 'same-origin' && site !== 'none') return false;
  return true;
}
