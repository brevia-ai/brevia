"""The behaviour of every store (``tests/store_contract.py``) on the store in memory."""

from __future__ import annotations

import pytest
from memory_store import MemoryStore

from store_contract import *  # noqa: F403  (the tests of the contract)

pytestmark = pytest.mark.unit


@pytest.fixture
def contract_store() -> MemoryStore:
    return MemoryStore()
