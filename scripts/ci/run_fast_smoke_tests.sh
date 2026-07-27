#!/usr/bin/env bash
# Blocking pytest gate for pull requests.
#
# A curated slice rather than the documented fast subset
# (-m "not gpu and not db and not ml and not firebird"): that subset is green but
# takes ~13 minutes and needs the full ML stack, which is too slow and too heavy
# to sit in front of every PR. It runs in the coverage workflow instead.
#
# These files cover the security, config and dispatch surfaces that break most
# often and import cleanly from requirements/requirements_ci.txt alone (~11s).
#
# See docs/testing/CI_GATES.md.
set -euo pipefail

python -m pytest -q -p no:cacheprovider \
  tests/test_api_security.py \
  tests/test_api_v2_reorg.py \
  tests/test_command_dispatcher.py \
  tests/test_config_environment.py \
  tests/test_config_secrets.py \
  tests/test_db_security.py
