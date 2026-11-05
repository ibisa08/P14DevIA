"""Traçage MLflow : optionnel, jamais bloquant pour le démarrage."""

import logging
import sys
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent

from config import Settings
from tracing import EXPERIMENT_NAME, setup_tracing

BASE = {"jwt_secret": "x" * 32, "llm_model": "test"}


def make_settings(tracking_uri: str | None) -> Settings:
    return Settings(_env_file=None, **BASE, mlflow_tracking_uri=tracking_uri)


class FakeMlflow:
    """Faux module mlflow qui enregistre ce que tracing.py lui demande."""

    def __init__(self, fail_on: str | None = None):
        self.calls: list[tuple[str, str | None]] = []
        self.fail_on = fail_on
        self.pydantic_ai = SimpleNamespace(autolog=lambda: self._record("autolog"))

    def _record(self, name: str, arg: str | None = None) -> None:
        if name == self.fail_on:
            raise ConnectionError("serveur MLflow injoignable")
        self.calls.append((name, arg))

    def set_tracking_uri(self, uri: str) -> None:
        self._record("set_tracking_uri", uri)

    def set_experiment(self, name: str) -> None:
        self._record("set_experiment", name)


def test_disabled_without_tracking_uri(monkeypatch: pytest.MonkeyPatch):
    # Même si mlflow était importable, il n'est pas même importé sans variable
    monkeypatch.setitem(sys.modules, "mlflow", None)

    assert setup_tracing(make_settings(None)) is False
    # Une valeur vide dans le .env vaut absence de variable
    assert setup_tracing(make_settings("   ")) is False


def test_missing_mlflow_warns_and_continues(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    # None dans sys.modules : `import mlflow` lève ImportError, comme dans l'image Docker
    monkeypatch.setitem(sys.modules, "mlflow", None)
    caplog.set_level(logging.WARNING)

    assert setup_tracing(make_settings("http://localhost:5001")) is False

    assert "MLflow n'est pas installé" in caplog.text


def test_enabled_configures_mlflow(monkeypatch: pytest.MonkeyPatch):
    fake = FakeMlflow()
    monkeypatch.setitem(sys.modules, "mlflow", fake)
    # Remplacé pour ne pas instrumenter durablement les agents du reste de la suite de tests
    instrumented: list[bool] = []
    monkeypatch.setattr(Agent, "instrument_all", lambda *args, **kwargs: instrumented.append(True))

    assert setup_tracing(make_settings("http://localhost:5001")) is True

    assert fake.calls == [
        ("set_tracking_uri", "http://localhost:5001"),
        ("set_experiment", EXPERIMENT_NAME),
        ("autolog", None),
    ]
    # Spans détaillés (requêtes au modèle, outils) : les agents sont instrumentés
    assert instrumented == [True]


def test_disabled_does_not_instrument_agents(monkeypatch: pytest.MonkeyPatch):
    # Sans MLFLOW_TRACKING_URI (production, CI), aucune instrumentation n'est installée
    instrumented: list[bool] = []
    monkeypatch.setattr(Agent, "instrument_all", lambda *args, **kwargs: instrumented.append(True))

    assert setup_tracing(make_settings(None)) is False

    assert instrumented == []


def test_mlflow_failure_does_not_crash(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setitem(sys.modules, "mlflow", FakeMlflow(fail_on="set_experiment"))
    caplog.set_level(logging.WARNING)

    assert setup_tracing(make_settings("http://localhost:5001")) is False

    assert "Traçage MLflow désactivé" in caplog.text
    assert "ConnectionError" in caplog.text
