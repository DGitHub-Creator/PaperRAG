import logging
import json
from logging.handlers import RotatingFileHandler

import pytest

from backend.core import logging_config


def test_log_files_rotate_and_setup_is_idempotent(tmp_path, monkeypatch):
    root = logging.Logger("isolated")
    monkeypatch.setattr(logging_config.logging, "getLogger", lambda: root)
    monkeypatch.setattr(logging_config, "LOG_DIR", tmp_path)
    monkeypatch.setattr(logging_config, "LOG_FILE", tmp_path / "app.log")
    monkeypatch.setattr(logging_config, "LOG_MAX_BYTES", 100)
    monkeypatch.setattr(logging_config, "_initialized", False)
    try:
        logging_config.setup_root_logger()
        logging_config.setup_root_logger()
        assert len(root.handlers) == 2
        assert isinstance(root.handlers[1], RotatingFileHandler)
        root.debug("%s", "x" * 120)
        root.debug("%s", "y" * 120)
        assert (tmp_path / "app.log.1").exists()
    finally:
        for handler in root.handlers:
            handler.close()


def test_failed_setup_can_be_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(logging_config, "LOG_DIR", tmp_path / "blocked")
    monkeypatch.setattr(logging_config, "_initialized", False)
    (tmp_path / "blocked").write_text("file", encoding="utf-8")
    with pytest.raises(FileExistsError):
        logging_config.setup_root_logger()
    assert not logging_config._initialized


def test_request_trace_is_isolated_and_json_contains_it():
    token = logging_config.request_trace_id.set("request-1")
    try:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "消息", (), None)
        assert json.loads(logging_config.JsonFormatter().format(record))["trace_id"] == "request-1"
    finally:
        logging_config.request_trace_id.reset(token)
    assert logging_config.request_trace_id.get() == "-"
