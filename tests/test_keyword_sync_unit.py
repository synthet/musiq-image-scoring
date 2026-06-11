from modules import db_legacy as db


def test_sync_image_keywords_applies_confidence_and_source_maps(monkeypatch):
    class _FakeTx:
        def __init__(self):
            self.keyword_ids = {}
            self.insert_params = []

        def execute(self, sql, params=None):
            if sql.startswith("UPDATE OR INSERT INTO image_keywords"):
                self.insert_params.append(params)

        def query_one(self, sql, params=None):
            keyword_norm = params[0]
            if keyword_norm in self.keyword_ids:
                return {"keyword_id": self.keyword_ids[keyword_norm]}
            return None

        def execute_returning(self, sql, params=None):
            keyword_norm = params[0]
            keyword_id = len(self.keyword_ids) + 1
            self.keyword_ids[keyword_norm] = keyword_id
            return [{"keyword_id": keyword_id}]

    class _FakeConnector:
        def __init__(self):
            self.tx = _FakeTx()

        def run_transaction(self, callback):
            return callback(self.tx)

    connector = _FakeConnector()
    monkeypatch.setattr(db, "get_connector", lambda: connector)

    db._sync_image_keywords(
        7,
        "species:American Robin,Birds",
        source="auto",
        confidence=0.25,
        relevance_weight=0.5,
        confidence_map={"species:american robin": 0.82},
        source_map={"species:american robin": "bioclip"},
    )

    assert connector.tx.insert_params == [
        (7, 1, "bioclip", 0.82, 0.5),
        (7, 2, "auto", 0.25, 0.5),
    ]


def _run_sync(monkeypatch, **kwargs):
    class _FakeTx:
        def __init__(self):
            self.keyword_ids = {}
            self.insert_params = []

        def execute(self, sql, params=None):
            if sql.startswith("UPDATE OR INSERT INTO image_keywords"):
                self.insert_params.append(params)

        def query_one(self, sql, params=None):
            keyword_norm = params[0]
            if keyword_norm in self.keyword_ids:
                return {"keyword_id": self.keyword_ids[keyword_norm]}
            return None

        def execute_returning(self, sql, params=None):
            keyword_norm = params[0]
            keyword_id = len(self.keyword_ids) + 1
            self.keyword_ids[keyword_norm] = keyword_id
            return [{"keyword_id": keyword_id}]

    class _FakeConnector:
        def __init__(self):
            self.tx = _FakeTx()

        def run_transaction(self, callback):
            return callback(self.tx)

    connector = _FakeConnector()
    monkeypatch.setattr(db, "get_connector", lambda: connector)
    db._sync_image_keywords(7, "Birds,Forest", **kwargs)
    return connector.tx.insert_params


def test_sync_image_keywords_applies_per_keyword_relevance_map(monkeypatch):
    params = _run_sync(
        monkeypatch,
        source="auto",
        confidence=0.4,
        relevance_weight=1.0,
        relevance_map={"birds": 0.91},
    )
    # birds gets the per-keyword override; forest falls back to the scalar.
    assert params == [
        (7, 1, "auto", 0.4, 0.91),
        (7, 2, "auto", 0.4, 1.0),
    ]


def test_sync_image_keywords_relevance_map_ignores_bad_values(monkeypatch):
    params = _run_sync(
        monkeypatch,
        relevance_weight=1.0,
        relevance_map={"birds": "not-a-number"},
    )
    # Non-numeric override is dropped; scalar default applies to both.
    assert params == [
        (7, 1, "auto", 1.0, 1.0),
        (7, 2, "auto", 1.0, 1.0),
    ]
