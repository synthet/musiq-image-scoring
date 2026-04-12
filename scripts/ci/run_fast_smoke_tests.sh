#!/usr/bin/env bash
set -euo pipefail

python -m pytest -q \
  tests/test_api_security.py \
  tests/test_api_v2_reorg.py \
  tests/test_command_dispatcher.py \
  tests/test_config_environment.py \
  tests/test_config_secrets.py \
  tests/test_db_security.py
