#!/bin/sh
# Installs the AIF git hooks into .git/hooks.
set -e
cd "$(git rev-parse --show-toplevel)"
for hook in commit-msg pre-commit; do
  cp "scripts/$hook" ".git/hooks/$hook"
  chmod +x ".git/hooks/$hook"
  echo "installed $hook"
done
