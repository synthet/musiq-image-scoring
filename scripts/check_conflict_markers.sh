#!/usr/bin/env bash
set -euo pipefail

# Scan tracked source files for unresolved merge conflict markers.
# Intentionally limited to source-like extensions under modules/, tests/, scripts/
# to avoid false positives in documentation divider content.

ROOTS=(modules tests scripts)

is_source_file() {
  case "$1" in
    *.py|*.sh|*.bash|*.zsh|*.ps1|*.bat|*.cmd|*.yml|*.yaml|*.json|*.toml|*.ini|*.cfg|*.sql|*.js|*.jsx|*.ts|*.tsx)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

tracked_files=()
for root in "${ROOTS[@]}"; do
  while IFS= read -r -d '' file; do
    if is_source_file "$file"; then
      tracked_files+=("$file")
    fi
  done < <(git ls-files -z -- "$root")
done

if [ ${#tracked_files[@]} -eq 0 ]; then
  echo "No tracked source files found in ${ROOTS[*]}; skipping conflict marker check."
  exit 0
fi

pattern='^(<<<<<<<|>>>>>>>|={7}$)'

if command -v rg >/dev/null 2>&1; then
  if rg --line-number --with-filename --color=never -e "$pattern" -- "${tracked_files[@]}"; then
    echo
    echo "❌ Unresolved merge conflict markers detected."
    exit 1
  fi
else
  # Fallback to grep -E when ripgrep is not available on the runner.
  if grep -HnE "$pattern" -- "${tracked_files[@]}"; then
    echo
    echo "❌ Unresolved merge conflict markers detected."
    exit 1
  fi
fi

echo "✅ No unresolved merge conflict markers found in tracked source files."
