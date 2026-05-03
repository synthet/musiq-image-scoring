#!/usr/bin/env bash
# On-demand Postgres backup — same workflow as .cursor/commands/backup-db.md
# (merged config, primary repo folder, optional Dropbox mirror + retention).
#
# Usage (from repo root or anywhere):
#   bash scripts/run_postgres_backup.sh
#   MIRROR_RETENTION_DAYS=0 bash scripts/run_postgres_backup.sh
#   BACKUP_DIR=/custom bash scripts/run_postgres_backup.sh
#   bash scripts/run_postgres_backup.sh -- -RetentionDays 7
#
# Environment (optional overrides):
#   CONFIG_PATH           — alternate config.json
#   BACKUP_DIR            — primary dump folder (default: <repo>/backups/postgres)
#   RETENTION_DAYS        — prune primary dumps older than N days (default: 30, 0=skip)
#   MIRROR_DIR            — mirror folder (default: Windows D:\Dropbox\Photos\Scoring)
#   MIRROR_RETENTION_DAYS — prune mirror dumps older than N days (default: 7, 0=no prune)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PS_SCRIPT="$REPO_ROOT/scripts/powershell/Backup-Postgres.ps1"

DEFAULT_MIRROR_WINDOWS='D:\Dropbox\Photos\Scoring'
MIRROR_DIR="${MIRROR_DIR:-$DEFAULT_MIRROR_WINDOWS}"
MIRROR_RETENTION_DAYS="${MIRROR_RETENTION_DAYS:-7}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
BACKUP_DIR="${BACKUP_DIR:-}"
CONFIG_PATH="${CONFIG_PATH:-}"

is_wsl() {
  grep -qi microsoft /proc/version 2>/dev/null || false
}

# Convert a path for Windows PowerShell -File / -MirrorDir (WSL or MSYS → host Windows).
to_windows_path_if_needed() {
  local path="$1"
  if [[ -z "$path" ]]; then
    printf '%s' ""
    return
  fi
  if command -v wslpath >/dev/null 2>&1 && is_wsl && [[ "$path" == /* ]]; then
    wslpath -w "$path"
    return
  fi
  if command -v cygpath >/dev/null 2>&1 && [[ "$path" == /* || "$path" =~ ^[A-Za-z]: ]]; then
    cygpath -w "$path" 2>/dev/null || printf '%s' "$path"
    return
  fi
  printf '%s' "$path"
}

powershell_launcher() {
  if command -v powershell.exe >/dev/null 2>&1; then
    printf '%s' powershell.exe
    return 0
  fi
  local winps="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
  if [[ -x "$winps" ]]; then
    printf '%s' "$winps"
    return 0
  fi
  return 1
}

pwsh_launcher() {
  command -v pwsh >/dev/null 2>&1 && printf '%s' pwsh && return 0
  return 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,20p' "$0"
  exit 0
fi

EXTRA_PS_ARGS=()
if [[ "${1:-}" == "--" ]]; then
  shift
  EXTRA_PS_ARGS+=("$@")
fi

USE_WIN_PATHS=0
ARGS=(
  "-NoProfile"
  "-ExecutionPolicy"
  "Bypass"
  "-File"
)

if PS_EXE="$(powershell_launcher)"; then
  USE_WIN_PATHS=1
  ARGS+=("$(to_windows_path_if_needed "$PS_SCRIPT")")
elif PS_EXE="$(pwsh_launcher)"; then
  ARGS+=("$PS_SCRIPT")
else
  echo "run_postgres_backup.sh: neither powershell.exe (WSL/Git Bash) nor pwsh found." >&2
  echo "Install PowerShell, or run: powershell -File scripts\\powershell\\Backup-Postgres.ps1 ..." >&2
  exit 1
fi

MIRROR_ARG="$MIRROR_DIR"
if [[ "$USE_WIN_PATHS" == 1 ]]; then
  if [[ "$MIRROR_DIR" == /* ]] || [[ "$MIRROR_DIR" == /mnt/* ]]; then
    MIRROR_ARG="$(to_windows_path_if_needed "$MIRROR_DIR")"
  fi
fi

path_for_param() {
  local p="$1"
  if [[ "$USE_WIN_PATHS" == 1 ]]; then
    to_windows_path_if_needed "$p"
  else
    printf '%s' "$p"
  fi
}

if [[ -n "${CONFIG_PATH}" ]]; then
  ARGS+=("-ConfigPath" "$(path_for_param "${CONFIG_PATH}")")
fi
if [[ -n "${BACKUP_DIR}" ]]; then
  ARGS+=("-BackupDir" "$(path_for_param "${BACKUP_DIR}")")
fi

ARGS+=("-RetentionDays" "$RETENTION_DAYS")
ARGS+=("-MirrorDir" "$MIRROR_ARG")
ARGS+=("-MirrorRetentionDays" "$MIRROR_RETENTION_DAYS")

if [[ ${#EXTRA_PS_ARGS[@]} -gt 0 ]]; then
  ARGS+=("${EXTRA_PS_ARGS[@]}")
fi

cd "$REPO_ROOT"
exec "$PS_EXE" "${ARGS[@]}"
