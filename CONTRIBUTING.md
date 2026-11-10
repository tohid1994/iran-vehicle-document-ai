# Contributing

Use a virtual environment and install `.[dev]`. Run Ruff, pytest and a package
build before submitting a PR. Changes should preserve the v1 schema and offline
runtime invariant. Include tests for new validators or adapter behavior.

Only use generated/synthetic fixtures. Do not upload real vehicle/owner data,
screenshots, secrets, proprietary fonts or unlicensed datasets. Accuracy claims
require an independently reviewable evaluation protocol, privacy-safe aggregate
metrics and clear dataset provenance. New models must specify license, immutable
revision, checksums and offline packaging. Keep application-specific integration
outside the core package.
