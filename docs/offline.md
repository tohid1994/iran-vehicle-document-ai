# Offline preparation and deployment

## Preferred: sealed Docker image

On an online machine with the target architecture, prepare models and build the
Docker image following README. Run a smoke extraction before exporting it.
`docker save` includes Python, native runtime, dependencies and models. Transfer
its tar through your trusted channel and use `docker load` offline. No runtime
model download path exists. You can enforce outbound isolation with host firewall
rules or an internal Docker network; keep the inbound API reachable only to
trusted backend callers.

## Native wheel bundle

On the same OS/architecture/Python as your target:

```bash
python scripts/prepare_offline.py --output offline-bundle
```

This explicitly online script downloads models and builds/downloads wheels.
It does **not** include Python itself, the native Tesseract executable or its
shared libraries. Supply those using your OS's complete offline package closure,
or use the Docker image. Do not copy arbitrary single binaries across platforms.

On the target:

```bash
python -m venv .venv
. .venv/bin/activate
pip install --no-index --find-links offline-bundle/wheelhouse iran-vehicle-document-ai
export IVDAI_MODEL_DIR="$PWD/offline-bundle/models"
vehicle-document-ai extract /private/vehicle.jpg --models "$IVDAI_MODEL_DIR" -o /private/result.json
```

Preparation records the exact upstream model revision and hashes. Runtime rejects
missing or modified model files. Preserve `manifest.json` alongside models;
make the directory read-only. The Python dependency ranges in pyproject are not
a universal reproducibility lock. Archive the actual wheelhouse and Docker image
used for your deployment, including hashes (e.g. `sha256sum`), OS architecture,
Python and `tesseract --version`. Rebuilding on a later day can resolve newer
compatible packages and apt packages.

## CPUs without AVX2

The adapter does not require Paddle/PyTorch. However installed native NumPy,
OpenCV and Tesseract binaries determine instruction requirements. Source-build
these libraries for the target CPU if generic distribution packages do not run.
Validate `tesseract --version`, imports and a synthetic extraction on the physical
server. No AVX2-less target was available in the current verification environment;
this configuration is conditional, not certified.

## Runtime controls

- `IVDAI_MODEL_DIR`: local verified model directory.
- `IVDAI_API_KEY`: optional shared secret in `x-api-key` (required by compose).
- `IVDAI_TIMEOUT`: overall API process timeout and OCR timeout, default 30 s.
- `IVDAI_CONCURRENCY`: API worker capacity per server process, default 1.
- `IVDAI_WORKER_MEMORY_MB`: POSIX worker address-space limit, default 2048 MiB.

Address space differs from RSS; tune with native runtimes and enforce a container
RSS/RAM limit too. Settings for package/CLI inputs are in `core.Settings`.
Production process managers multiply capacities by their process count. For the
package/CLI, the OCR subprocess timeout is enforced but decoding/preprocessing
are not hard-preempted; use the REST service/container for hard job isolation.
Workers are terminated as a process group on POSIX and their private temporary
directory is cleaned by the API parent even after timeout. On Windows use an
external process supervisor/job-object policy for descendant process termination;
the API's POSIX process-group guarantee does not apply.


### Regional refinement assets

Run model preparation with the Python dependencies already installed. On Debian/
Ubuntu also install `fonts-noto-core` and `fonts-dejavu-core` during preparation.
`prepare_models.py` fetches the pinned Persian refinement model and invokes
`prepare_digit_templates.py`. The latter uses synthetic glyphs from installed
Noto/DejaVu fonts and writes a safe NumPy archive, provenance hashes and font license
notices to the local models directory. Transfer this entire directory offline.
Inference requires neither system fonts nor network access. To prepare templates
with custom font paths use `prepare_digit_templates.py --fonts PATH --font-license
LICENSE_PATH` (repeat the license option for multiple notices).
