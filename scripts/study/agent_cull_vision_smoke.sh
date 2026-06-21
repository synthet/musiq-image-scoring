#!/usr/bin/env bash
# Direct CLI vision smoke: verify provider can read a thumbnail path on disk.
set -euo pipefail

IMAGE_PATH="${1:-}"
PROVIDER="${2:-antigravity}"
IMAGE_ID="${3:-0}"

if [[ -z "$IMAGE_PATH" ]]; then
  echo "Usage: $0 <thumbnail_path> [antigravity|codex|gemini] [image_id]" >&2
  exit 2
fi

if [[ ! -f "$IMAGE_PATH" ]]; then
  python3 -c "import json; print(json.dumps({'ok': False, 'error': 'path_not_found', 'path': '$IMAGE_PATH'}))"
  exit 2
fi

PROMPT="Read the image file at this exact path: ${IMAGE_PATH}
Reply with JSON only (no markdown): {\"image_id\": ${IMAGE_ID}, \"species\": \"...\", \"focus_ok\": true/false, \"blur_foreground\": true/false, \"visual_note\": \"one sentence\"}"

case "$PROVIDER" in
  antigravity)
    if [[ -x /app/scripts/wsl/antigravity_agent.sh ]]; then
      CMD=(/app/scripts/wsl/antigravity_agent.sh -p "$PROMPT")
    else
      CMD=(agy -p "$PROMPT" --dangerously-skip-permissions)
    fi
    ;;
  codex)
    SANDBOX="${CODEX_SANDBOX:-workspace}"
    CMD=(codex exec --sandbox "$SANDBOX" --ask-for-approval never --json "$PROMPT")
    ;;
  gemini)
    if [[ -x /app/scripts/wsl/gemini_agent.sh ]]; then
      CMD=(/app/scripts/wsl/gemini_agent.sh --skip-trust -p "$PROMPT")
    else
      CMD=(gemini --skip-trust --output-format json -p "$PROMPT")
    fi
    ;;
  *)
    python3 -c "import json; print(json.dumps({'ok': False, 'error': 'unknown_provider', 'provider': '$PROVIDER'}))"
    exit 2
    ;;
esac

TMP_OUT="$(mktemp)"
TMP_ERR="$(mktemp)"
START=$(date +%s)
set +e
"${CMD[@]}" >"$TMP_OUT" 2>"$TMP_ERR"
CODE=$?
set -e
END=$(date +%s)

python3 - "$TMP_OUT" "$TMP_ERR" "$CODE" "$PROVIDER" "$IMAGE_PATH" "$((END - START))" <<'PY'
import json, sys
out_path, err_path, code_s, provider, path, duration_s = sys.argv[1:7]
code = int(code_s)
out = open(out_path, encoding="utf-8", errors="replace").read()
err = open(err_path, encoding="utf-8", errors="replace").read()
visual_tokens = ("blur", "focus", "sharp", "soft", "deer", "fawn", "subject", "foreground", "background")
lower = (out + err).lower()
has_visual = any(t in lower for t in visual_tokens)
print(json.dumps({
    "ok": code == 0,
    "provider": provider,
    "exit_code": code,
    "duration_s": int(duration_s),
    "path": path,
    "has_visual_language": has_visual,
    "stdout_head": out[:2000],
    "stderr_head": err[:500],
}, indent=2))
PY

rm -f "$TMP_OUT" "$TMP_ERR"
exit "$CODE"
