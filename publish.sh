#!/usr/bin/env zsh
set -euo pipefail

echo "==> Cleaning old builds..."
rm -rf dist/ build/ src/*.egg-info 2>/dev/null || true

echo "==> Building package..."
python3 -m build

echo "==> Uploading to PyPI..."
twine upload dist/*

echo "==> Done! Published $(grep 'version' pyproject.toml | head -1)"
