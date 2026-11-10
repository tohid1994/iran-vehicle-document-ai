#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
gh auth status
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init -b main
  git add .
  git -c user.name='Iran Vehicle Document AI contributors' -c user.email='noreply@localhost' commit -m 'Implement offline vehicle document reader'
fi
owner=$(gh api user --jq .login)
if gh repo view "$owner/iran-vehicle-document-ai" >/dev/null 2>&1; then
  echo 'Repository already exists. Inspect it before pushing; no files overwritten.' >&2
  exit 1
fi
gh repo create "$owner/iran-vehicle-document-ai" --public --source=. --remote=origin --push
