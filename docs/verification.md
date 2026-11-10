# Verification record — 2026-11-10

This is an initial implementation verification, not a real-document benchmark.

## Passed in this workspace

- 28 pytest checks: digit normalization, national-ID checksum, VIN syntax,
  label/geometry mapping, ambiguity abstention, null confidence and unknown values,
  decoding JPEG/PNG/WebP, rejecting non-raster/GIF/oversize/overpixel input,
  template bounds, optional rectification/CLAHE, blank results, API auth/schema,
  sanitized errors, chunked request limits, missing models, model tamper rejection,
  timeout termination/parent-owned temporary cleanup, and actual English OCR
  on a generated image.
- Ruff lint and formatting.
- `python -m build --no-isolation`: wheel and source distribution built.
- Installed built wheel into a dedicated virtual environment (reusing available
  system dependency packages); exercised installed CLI against a synthetic image.
- Downloaded immutable upstream `fas`/`eng` models during explicit preparation,
  verified their SHA-256 hashes, and called actual local Tesseract through the
  process-isolated API `analyze` endpoint: HTTP 200 with 7 word regions.
  This mixed Persian/English smoke image did not yield all digits correctly;
  it verifies runtime execution, not accurate document extraction.
- Source/model payloads contain no real user registration documents or credentials.

The runner used Linux x86_64 / Python 3.12 / locally installed Tesseract.
Two third-party test-runner deprecation warnings were present; no test failed.
No external image-processing service was called by the implementation. A kernel-
enforced network-denial test was not run; offline guarantees are based on the
local-only implementation and model fail-closed checks, not a firewall trace.

## Not verified / intentionally incomplete

- Accuracy, field correctness rates, recall, confidence calibration and genuine
  document detection on a real registration dataset.
- AVX2-less CPUs, ARM, Windows native deployment and GPU runtimes.
- Docker build/run: Docker executable is unavailable in this workspace.
- A complete native offline OS/Python/Tesseract/dependency closure. Model files are
  included in the delivery archive; Python dependencies and native Tesseract must
  be prepared for the target or sealed in an image using the supplied instructions.
- GitHub Actions execution: workflow file is written but has not run on GitHub.
- GitHub publication: the public repository now exists at
  https://github.com/tohid1994/iran-vehicle-document-ai . Initial source, MIT license,
  documentation and CI configuration are included in this publication. Check the
  Actions tab for the independently executed CI result; local checks above are
  distinct from GitHub-hosted verification.

Model binaries are intentionally excluded from git. Run the explicit online
preparation script and use the recorded revision/checksums for offline packaging.
