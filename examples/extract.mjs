// Node.js 20+. Keep this on your trusted backend; do not embed API keys in browser code.
import { readFile } from 'node:fs/promises';
const form = new FormData();
form.append('file', new Blob([await readFile(process.argv[2])]), 'document.jpg');
const response = await fetch('http://127.0.0.1:8000/api/v1/documents/extract', {
  method: 'POST',
  headers: { 'x-api-key': process.env.IVDAI_API_KEY ?? '' },
  body: form,
  signal: AbortSignal.timeout(35000),
});
if (!response.ok) throw new Error(`Document extraction failed: HTTP ${response.status}`);
const result = await response.json();
// Return to your private application flow; avoid logging identities or document data.
process.stdout.write(JSON.stringify(result, null, 2) + '\n');
