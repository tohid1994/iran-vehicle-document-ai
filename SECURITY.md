# Security and privacy

Never publish real documents, identity fields, credentials, request bodies or
extraction results in issues, CI artifacts or logs. Report security issues
privately to the repository maintainer without a real registration attachment.

Inputs are restricted by bytes/pixels/dimensions/format; actual raster decoding,
not a filename or MIME claim, determines acceptance. Animated images and other
formats are rejected. Keep Pillow, OpenCV and Tesseract patched. Malformed-image
protection reduces risk but does not prove that native decoders have no flaws;
run the service as non-root inside the supplied constrained container.

The HTTP body limiter runs before multipart parsing; OCR concurrency is bounded,
and API processing is in disposable workers. Expected errors are fixed codes;
no raw OCR text, filenames or decoder stderr are returned as exception details.
The application doesn't log documents. Runtime/operating-system/core-dump,
reverse-proxy and APM settings are your responsibility: disable body capture,
core dumps, tracing of response content and public cache/storage. API responses
should only be returned to authorized backend callers.

Set a high-entropy `IVDAI_API_KEY` via secret injection, never commit it. Compare
keys in constant time. For shared or network deployment put the service behind
TLS and a reverse proxy that enforces authentication, per-client quotas, request
rate limits (e.g. 5/minute), request size/time limits and trusted source networks.
The built-in API key is not multi-tenant authorization; there is no built-in
per-identity rate limiter, account management or audit storage. Capacity rejection
(429) is resource protection, not a replacement for gateway rate limiting.

API files are deleted after processing including ordinary failures/timeouts.
CLI outputs persist only when explicitly requested; stdout also carries sensitive
JSON. Use encrypted storage, restrictive permissions and a retention policy if
you choose to persist results. Avoid filenames/URLs containing identity data.
