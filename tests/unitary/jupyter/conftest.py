from multiprocessing.shared_memory import SharedMemory
from os import urandom
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def nest_asyncio_mock(replace_modules):
    mock = MagicMock()
    mock.authenticated = lambda x: x
    replace_modules({"nest_asyncio": mock})
    return mock


@pytest.fixture()
def shared_memory_length(nest_asyncio_mock):
    from boa.integrations.jupyter.constants import SHARED_MEMORY_LENGTH

    return SHARED_MEMORY_LENGTH


@pytest.fixture()
def token():
    from boa.integrations.jupyter.constants import CALLBACK_TOKEN_BYTES, PLUGIN_NAME

    return f"{PLUGIN_NAME}_{urandom(CALLBACK_TOKEN_BYTES).hex()}"


@pytest.fixture()
def shared_memory(token, shared_memory_length):
    memory = SharedMemory(name=token, create=True, size=shared_memory_length)
    yield memory
    memory.unlink()
