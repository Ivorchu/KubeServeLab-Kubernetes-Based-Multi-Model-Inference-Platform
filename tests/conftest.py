import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from shared.protocol import InferenceJob
from services.api.app.database import get_db
from services.api.app.main import app


@pytest.fixture
def sample_job():
    return InferenceJob(
        request_id="test-request-id",
        model="text-small",
        input="this is a test sentence",
        created_at=time.time(),
    )


@pytest.fixture(autouse=True)
def mock_db_dependency():
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.execute = AsyncMock(return_value=execute_result)

    async def _dep():
        yield mock_session

    app.dependency_overrides[get_db] = _dep
    yield mock_session
    app.dependency_overrides.pop(get_db, None)
