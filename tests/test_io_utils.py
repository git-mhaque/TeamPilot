import json
from pathlib import Path

import pytest

from scripts.io_utils import (
    InitiativeLoadError,
    load_epic_keys_from_initiatives,
    load_initiatives,
    merge_initiatives_with_epic_metrics,
)


def _write_initiatives(path: Path, content):
    path.write_text(json.dumps(content), encoding="utf-8")


def test_load_epic_keys_from_initiatives_success(tmp_path, monkeypatch):
    monkeypatch.setenv("TEAM_BEACON_CONFIG_DIR", str(tmp_path))
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
    monkeypatch.setenv("TEAM_BEACON_CONFIG_DIR", str(tmp_path))
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
    monkeypatch.setenv("TEAM_BEACON_CONFIG_DIR", str(tmp_path))
    initiatives_path = tmp_path / "initiatives.json"
    _write_initiatives(initiatives_path, bad_content)

    with pytest.raises(InitiativeLoadError):
        load_epic_keys_from_initiatives()


def test_load_initiatives_returns_structure(tmp_path, monkeypatch):
    monkeypatch.setenv("TEAM_BEACON_CONFIG_DIR", str(tmp_path))
    initiatives_path = tmp_path / "initiatives.json"
    sample = [{"group": "G", "epics": [{"key": "E"}]}]
    _write_initiatives(initiatives_path, sample)

    result = load_initiatives()

    assert result == sample
    assert result is not sample  # ensure new list, not same reference


def test_merge_initiatives_with_epic_metrics_enriches_data():
    initiatives = [
        {
            "group": "G",
            "epics": [
                {"key": "E1", "description": "Original"},
                {"key": "E2"},
            ],
        }
    ]
    epic_dataset = [
        {
            "issue_number": "E1",
            "title": "Epic One",
            "link": "http://jira/E1",
            "total_issues": 5,
            "completed": 3,
            "inprogress": 1,
            "todo": 1,
            "percentage_done": 60.0,
            "percentage_inprogress": 20.0,
            "percentage_todo": 20.0,
        }
    ]

    enriched = merge_initiatives_with_epic_metrics(initiatives, epic_dataset)

    assert enriched[0]["group"] == "G"
    e1, e2 = enriched[0]["epics"]
    assert e1["description"] == "Original"
    assert e1["title"] == "Epic One"
    assert e1["total_issues"] == 5
    assert e1["percentage_done"] == 60.0
    assert e2 == {"key": "E2"}

    # ensure original input not mutated
    assert initiatives[0]["epics"][0].get("title") is None