import pytest

from contactapp.__main__ import main
from contactapp.envfile import read_keys


def test_only_wanted_keys_are_read(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# c\nSLACK=zzz\nexport HUBSPOT_TOKEN='abc'\nHUBSPOT_PORTAL_ID=42\nOTHER=1\n")
    assert read_keys(f, ("HUBSPOT_TOKEN", "HUBSPOT_PORTAL_ID")) == {"HUBSPOT_TOKEN": "abc", "HUBSPOT_PORTAL_ID": "42"}


def test_push_flag_needs_a_token():
    with pytest.raises(SystemExit):
        main(["--allow-crm-push"])


def test_missing_env_file_is_a_clear_error(tmp_path):
    with pytest.raises(SystemExit) as err:
        main(["--crm-env-file", str(tmp_path / "nope.env")])
    assert "Cannot read" in str(err.value)


def test_env_file_without_token_exits(tmp_path):
    f = tmp_path / ".env"
    f.write_text("X=1\n")
    with pytest.raises(SystemExit):
        main(["--crm-env-file", str(f)])
