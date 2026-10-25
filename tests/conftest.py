import os
import sys
import importlib.util
import asyncio

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


@pytest.fixture
def load_isolated_module():
    """Exercise import-time settings without replacing modules used by other tests.

    Replacing database/main in sys.modules leaves previously imported route
    dependencies pointing at a different module than later monkeypatches.
    """

    def load(name):
        spec = importlib.util.find_spec(name)
        package, _, leaf = name.rpartition(".")
        isolated = importlib.util.spec_from_file_location(
            f"{package}._test_{leaf}", spec.origin
        )
        module = importlib.util.module_from_spec(isolated)
        isolated.loader.exec_module(module)
        return module

    return load


@pytest.fixture(scope="session", autouse=True)
def close_application_database():
    """Release the shared app pool that direct service tests may open."""
    yield
    database = sys.modules.get("landppt.database.database")
    if database is not None:
        asyncio.run(database.close_db())
