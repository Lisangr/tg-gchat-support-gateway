from unittest.mock import MagicMock, patch

import requests

from src.gchat_client import GChatClient
from src.state_db import StateDB


def test_state_db_offset_and_cleanup():
    db = StateDB(":memory:")
    assert db.get_tg_offset() == 0

    db.set_tg_offset(42)
    assert db.get_tg_offset() == 42

    db.mark_processed("tg:1")
    assert db.is_processed("tg:1") is True
    assert db.cleanup_processed_messages(retention_days=7) == 0
    db.close()


@patch("src.gchat_client.service_account.Credentials.from_service_account_file")
def test_gchat_pubsub_read_timeout_returns_empty(mock_creds):
    creds_instance = MagicMock()
    creds_instance.valid = True
    creds_instance.token = "fake-token"
    mock_creds.return_value = creds_instance

    client = GChatClient(
        sa_key_path="dummy.json",
        space_id="spaces/AAA",
        subscription="projects/p/subscriptions/s",
        pull_timeout=95,
    )
    session = MagicMock()
    session.post.side_effect = requests.exceptions.ReadTimeout("timed out")
    client._local.session = session

    events = client.pull_pubsub_events()
    assert events == []
