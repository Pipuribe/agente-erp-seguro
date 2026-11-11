from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.gateway import Gateway
from app.odoo.mock import MockOdoo
from app.store import Store


@pytest.fixture
def settings():
    return Settings(approval_token="secret", db_path=":memory:")


@pytest.fixture
def backend():
    return MockOdoo()


@pytest.fixture
def store():
    return Store(":memory:")


@pytest.fixture
def gateway(backend, store, settings):
    return Gateway(backend, store, settings)


@pytest.fixture
def make_gateway(backend, store, settings):
    def _make(**overrides):
        return Gateway(backend, store, replace(settings, **overrides))
    return _make


class FakeLLM:
    """Cliente falso con la forma de anthropic.Anthropic().messages.create."""

    def __init__(self, script):
        self.script = list(script)
        self.messages = self

    def create(self, **kwargs):
        return self.script.pop(0)


def tool_use(name, input, id="t1"):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def text(t):
    return SimpleNamespace(type="text", text=t)


def resp(blocks, stop):
    return SimpleNamespace(content=blocks, stop_reason=stop)
