# Development

Hub page — canonical detail lives in linked docs.

## Environments and Python

- **[guides/setup/ENVIRONMENTS.md](guides/setup/ENVIRONMENTS.md)** — WSL vs Windows venvs, which venv for app vs pytest.
- **[guides/setup/WSL2_TENSORFLOW_GPU_SETUP.md](guides/setup/WSL2_TENSORFLOW_GPU_SETUP.md)** — GPU / CUDA setup.
- **[guides/setup/PYTHON_VERSION_CAVEATS.md](guides/setup/PYTHON_VERSION_CAVEATS.md)** — Python / dependency constraints.
- **[../README.md](../README.md)** — clone, `config.json`, Docker vs WSL quick paths.

## Cursor / AI rules

- **[../AGENTS.md](../AGENTS.md)** — MCP, commands, tool inventory.
- **[../.cursor/rules/python-wsl-webapp-env.mdc](../.cursor/rules/python-wsl-webapp-env.mdc)** — when to use WSL + `~/.venvs/tf` for scripts.

## Health check

- **[DIAGNOSTICS.md](DIAGNOSTICS.md)** — `python scripts/doctor.py` and debug bundles.

## Sibling app (Electron gallery)

- **[image-scoring-gallery](https://github.com/synthet/image-scoring-gallery)** — `npm run dev`, `npm run doctor` (repo-local); keep clones **sibling** to this backend for `webui.lock` port discovery unless overridden in config.
