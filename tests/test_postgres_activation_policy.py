from tests import conftest as tests_conftest


class _ConfigStub:
    def __init__(self, marker_expr: str):
        self._marker_expr = marker_expr

    def getoption(self, name: str):
        if name == "-m":
            return self._marker_expr
        raise ValueError(name)


def test_postgres_activation_policy_is_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("RUN_POSTGRES_TESTS", raising=False)
    monkeypatch.delenv("SKIP_POSTGRES_TESTS", raising=False)

    assert tests_conftest._postgres_tests_enabled(_ConfigStub("")) is False
    assert tests_conftest._postgres_tests_enabled(_ConfigStub("postgres")) is True
    assert tests_conftest._postgres_tests_enabled(_ConfigStub("postgres and not slow")) is True
    assert tests_conftest._postgres_tests_enabled(_ConfigStub("not postgres")) is False

    monkeypatch.setenv("RUN_POSTGRES_TESTS", "1")
    assert tests_conftest._postgres_tests_enabled(_ConfigStub("")) is True

    monkeypatch.setenv("SKIP_POSTGRES_TESTS", "1")
    assert tests_conftest._postgres_tests_enabled(_ConfigStub("postgres")) is False
