from multiprocessing.shared_memory import SharedMemory
from os import urandom
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def tornado_mock(replace_modules):
    replace_modules({"tornado.web": MagicMock(authenticated=lambda x: x)})


@pytest.fixture()
def jupyter_module_mock(replace_modules, tornado_mock):
    jupyter_mock = MagicMock()
    utils = jupyter_mock.utils
    serverapp = jupyter_mock.serverapp
    base_handlers = jupyter_mock.base.handlers

    utils.url_path_join = lambda *args: "/".join(args)
    base_handlers.APIHandler = object

    replace_modules(
        {
            "jupyter_server.base.handlers": base_handlers,
            "jupyter_server.serverapp": serverapp,
            "jupyter_server.utils": utils,
        }
    )
    return jupyter_mock


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
