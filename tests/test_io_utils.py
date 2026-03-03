import json
from pathlib import Path

import pytest

from scripts.io_utils import InitiativeLoadError, load_epic_keys_from_initiatives


def _write_initiatives(path: Path, content):
    path.write_text(json.dumps(content), encoding="utf-8")


def test_load_epic_keys_from_initiatives_success(tmp_path, monkeypatch):
    monkeypatch.setenv("TEAM_BEACON_DATA_DIR", str(tmp_path))
    initiatives_path = tmp_path / "initiatives.json"
    _write_initiatives(
        initiatives_path,
        [
            {"group": "A", "epics": [{"key": "EPIC-1"}, {"key": "EPIC-2"}]},
            {"group": "B", "epics": [{"key": "EPIC-1"}, {"key": "EPIC-3"}]},
        ],
    )

    keys = load_epic_keys_from_initiatives()

    assert keys == ["EPIC-1", "EPIC-2", "EPIC-3"]


def test_load_epic_keys_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("TEAM_BEACON_DATA_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        load_epic_keys_from_initiatives()


@pytest.mark.parametrize(
    "bad_content",
    [
        {},
        ["not-a-dict"],
        [{"group": "A", "epics": "not-a-list"}],
        [{"group": "A", "epics": [{}]}],
        [{"group": "A", "epics": [{"key": 123}]}],
        [{"group": "A", "epics": []}],
        [],
    ],
)
def test_load_epic_keys_invalid_content(tmp_path, monkeypatch, bad_content):
    monkeypatch.setenv("TEAM_BEACON_DATA_DIR", str(tmp_path))
    initiatives_path = tmp_path / "initiatives.json"
    _write_initiatives(initiatives_path, bad_content)

    with pytest.raises(InitiativeLoadError):
        load_epic_keys_from_initiatives()