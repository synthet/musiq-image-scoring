#!/usr/bin/env bash
set -euo pipefail

# Fail the check if unresolved merge conflict markers exist in tracked source files.
# We intentionally scope this to code-heavy directories and source-like extensions,
# excluding markdown/docs where divider lines like "=======" are legitimate.

TARGET_DIRS=(modules tests scripts)
PATTERN='^(<<<<<<< .*$|=======$|>>>>>>> .*$)'

SOURCE_EXT_REGEX='\.(py|sh|bash|zsh|mjs|cjs|js|jsx|ts|tsx|ps1|bat|cmd|sql|toml|ini|cfg|conf|ya?ml)$'

mapfile -t tracked_files < <(git ls-files -- "${TARGET_DIRS[@]}")

scan_files=()
for file in "${tracked_files[@]}"; do
  if [[ "$file" =~ $SOURCE_EXT_REGEX ]]; then
    scan_files+=("$file")
  fi
done

if [[ ${#scan_files[@]} -eq 0 ]]; then
  echo "No tracked source files matched configured directories/extensions."
  exit 0
fi

if matches=$(rg --line-number --no-heading --color=never "$PATTERN" "${scan_files[@]}" 2>/dev/null); then
  if [[ -n "$matches" ]]; then
    echo "Unresolved conflict markers detected:"
    echo "$matches"
    exit 1
  fi
fi

echo "No unresolved conflict markers found in tracked source files."
