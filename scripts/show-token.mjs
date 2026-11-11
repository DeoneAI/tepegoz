// Print the collector token. Only needed to sign in from another device by hand;
// the dashboard on the collector PC (http://localhost:8787) works without it.
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
if (process.env.COLLECTOR_TOKEN) {
  console.log(process.env.COLLECTOR_TOKEN);
} else {
  const file = path.join(path.resolve(process.env.DATA_DIR || path.join(root, 'data')), '.collector-key');
  try {
    console.log((await readFile(file, 'utf8')).trim());
  } catch {
    console.error('No token yet. Run "npm start" once; it creates the token in data/.collector-key.');
    process.exitCode = 1;
  }
}
