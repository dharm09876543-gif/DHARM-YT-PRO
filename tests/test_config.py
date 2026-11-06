from src.config import (load_yaml, validate_all, validate_channels,
                        validate_schedules, validate_settings)


def test_example_configs_are_valid():
    assert validate_all() == []


def test_bad_privacy_and_cleanup():
    s = load_yaml("settings")
    s["uploads"]["default_privacy"] = "secret"
    s["drive"]["cleanup_mode"] = "delete"
    errs = validate_settings(s)
    assert any("default_privacy" in e for e in errs)
    assert any("cleanup_mode" in e for e in errs)


def test_duplicate_channel_and_bad_id():
    c = {"channels": [
        {"key": "A", "channel_id": "UC" + "x" * 22, "drive_folder_id": "f"},
        {"key": "A", "channel_id": "UC" + "x" * 22, "drive_folder_id": ""},
        {"key": "B", "channel_id": "bad", "drive_folder_id": "f", "timezone": "Mars/Base"},
    ]}
    errs = " | ".join(validate_channels(c))
    assert "duplicate key" in errs and "duplicate channel_id" in errs
    assert "drive_folder_id" in errs and "24 characters" in errs and "timezone" in errs


def test_bad_slots():
    errs = validate_schedules({"scheduler": {"timezone": "Asia/Kolkata", "slots": ["25:00", "9:00", "10:00", "10:00"]}})
    assert len(errs) == 3
