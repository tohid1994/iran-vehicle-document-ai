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


## Local correction after first real sample

The first real high-quality scan exposed cross-column extraction, mixed-script
hallucinations and an overly permissive success flag. The local correction adds
a guarded older-layout regional reader, separate scripts, raw-line segmentation,
quote-safe TSV parsing, plate alias/validation and stricter completion semantics.
The supplied real photo and its OCR/identity values are never included in source,
fixtures or public documentation. Synthetic geometry and text test the regressions.

This correction is included in the current source update. See the separate private result delivered to
the user for actual sample output; no generalized accuracy claim is made. Model,
color, plate and identifier OCR remain incomplete on the sample. Profile selection
assumes an aligned legacy form; photos with different layouts may not benefit.


## Color and national-ID follow-up

Color uses a native-scale grayscale Persian refinement pass. National ID uses
context OCR plus independent synthetic-font digit templates; it does not search
check digits or embed the example's identity in code. The same real scan is used
for a complete API rerun, with private output retained separately. Additional
regression tests cover missing/ambiguous glyphs, synthetic segmentation, model
checksum rejection, and the absence of checksum-driven digit completion. These
changes do not establish general accuracy on other documents.


## Current local transcription follow-up

The local reader now also segments the printed VIN grid, reads the old plate's
separate groups, and re-reads uncertain model words. A full REST execution on the
same supplied scan reads all required printed core values. Its printed VIN fails
standard syntax; the unmodified transcription is retained as raw evidence and is
not forced into a compliant identifier. `transcriptionComplete` distinguishes
this from `success`, which still requires valid normalized identifiers.

47 software checks pass, including missing-character abstention, preserving a
forbidden printed VIN letter, word reread evidence, unsupported-model abstention,
and rejecting an empty plate. These are development checks and one-sample
verification, not a general document accuracy benchmark. Changes are included in this source update;
no real image, owner data or actual identifiers are in the repository's sources.


## Current remaining-test run — 2026-11-11

65 software tests pass, plus lint, formatting, compile and package builds. Fresh
isolated wheelhouse installation and inference pass inside a disconnected network
namespace. Real loopback HTTP auth/extraction/no-store/log checks pass. Real worker
concurrency, hard timeout, cancellation, process-group termination, temporary
cleanup, recovery, 15-second stalled upload, and controlled memory failure pass.

The same-photo stability matrix has 11 cases: 6 exact field matches and 5 failures.
Padding, quarter-turns and lossless encoding match; 75%/125% size, +/-2-degree tilt
and JPEG quality-90 re-encoding still lose/change some fields. These failures are
not production acceptance passes. The local changes improve grid-based alignment
and safer abstention but do not resolve those remaining OCR robustness failures.

Official Docker binaries were prepared, but the environment denies the rootless
daemon's required Unix socket operation; Docker build/run could not be verified.
Software vector-feature fallback passes, not physical AVX2-less CPU certification.
No other real document was tested, no real data was added to source, and changes
are included in this source update. See the separately delivered privacy-safe test report.
