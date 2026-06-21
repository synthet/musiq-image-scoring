# Docker Gemini config stub

Compose mounts this empty directory to `/root/.gemini` in the `webui` container when
`GEMINI_CONFIG_SOURCE` is unset in `.env`.

For **agent cull review**, set `GEMINI_CONFIG_SOURCE` in `.env` to your host
`~/.gemini` (forward slashes). See `docs/guides/setup/agent-cull-review-gemini-cli.md`.
