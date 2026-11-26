import pytest

from hub.pipeline import Settings
from hub.scenarios import APPROVER


@pytest.fixture
def settings() -> Settings:
    return Settings("t" * 32, "s" * 32, response_url_prefix="http://fake.invalid/", approvers=(APPROVER,))
