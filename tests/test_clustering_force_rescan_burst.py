"""Force-rescan must clear the synthetic ``burst_uuid`` stamped by clustering.

Visual clustering writes a fresh ``uuid4`` into ``images.burst_uuid`` for every
stack (``modules/clustering.py``). The burst pre-grouping path reads that column
*before* visual clustering, so if a force rescan leaves it populated the old
grouping is re-imposed and the configured threshold/time_gap are bypassed. These
tests pin that both rescan paths null ``burst_uuid`` alongside ``stack_id``.
"""

from unittest.mock import MagicMock, patch

import modules.db_legacy as db_legacy


def _capture_tx_executes(connector, tx):
    """Wire ``connector.run_transaction`` to call the real ``_tx`` with ``tx``.

    Returns a list that accumulates every SQL string passed to ``tx.execute``.
    """
    executed: list[str] = []

    def _exec(sql, params=None):
        executed.append(sql)
        return 1

    tx.execute.side_effect = _exec
    connector.run_transaction.side_effect = lambda fn: fn(tx)
    return executed


def _image_updates(executed):
    return [s for s in executed if s.strip().upper().startswith("UPDATE IMAGES")]


def test_clear_cluster_progress_nulls_burst_uuid():
    connector = MagicMock()
    connector.query.return_value = []  # no running culling phases to reset
    tx = MagicMock()
    executed = _capture_tx_executes(connector, tx)

    with patch.object(db_legacy, "get_connector", return_value=connector):
        db_legacy.clear_cluster_progress()

    updates = _image_updates(executed)
    assert updates, "expected an UPDATE images statement"
    assert all("burst_uuid = NULL" in s for s in updates)


def test_clear_stacks_in_folder_nulls_burst_uuid():
    connector = MagicMock()
    tx = MagicMock()
    # folder lookup -> id 1; per-stack remaining count -> 0 (stack gets deleted)
    tx.query_one.side_effect = [{"id": 1}, {"cnt": 0}]
    # distinct stack ids for the folder, then the running-culling lookup
    tx.query.side_effect = [[{"stack_id": 10}], []]
    executed = _capture_tx_executes(connector, tx)

    with patch.object(db_legacy, "get_connector", return_value=connector):
        ok, _msg = db_legacy.clear_stacks_in_folder("/photos/deer")

    assert ok is True
    updates = _image_updates(executed)
    assert updates, "expected an UPDATE images statement"
    assert all("burst_uuid = NULL" in s for s in updates)
