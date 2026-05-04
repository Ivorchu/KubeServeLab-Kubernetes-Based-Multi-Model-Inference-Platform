"""
pytest.ini sets PYTHONPATH=. so all imports resolve from the project root.
This conftest provides shared fixtures used across test modules.
"""
import pytest


@pytest.fixture
def sample_job():
    import time
    from shared.protocol import InferenceJob

    return InferenceJob(
        request_id="test-request-id",
        model="text-small",
        input="this is a test sentence",
        created_at=time.time(),
    )
