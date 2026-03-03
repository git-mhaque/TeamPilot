"""Shared file IO helpers."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from copy import deepcopy
from typing import Iterable, Mapping


class InitiativeLoadError(RuntimeError):
    """Raised when initiatives.json cannot be parsed into epic keys."""


def _load_and_validate_initiatives(filename: str | os.PathLike) -> list[dict]:
    path = Path(filename)
    try:
        with path.open("r", encoding="utf-8") as fh:
            content = json.load(fh)
    except FileNotFoundError as exc:  # pragma: no cover - direct failure path
        raise FileNotFoundError(f"Initiatives file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InitiativeLoadError(f"Initiatives file is not valid JSON: {path}") from exc

    if not isinstance(content, list):
        raise InitiativeLoadError("Initiatives file must contain a list of groups")

    for group in content:
        if not isinstance(group, dict):
            raise InitiativeLoadError("Each initiative entry must be an object")
        epics = group.get("epics", [])
        if not isinstance(epics, list):
            raise InitiativeLoadError("'epics' must be a list for each initiative group")
        for epic in epics:
            if not isinstance(epic, dict) or "key" not in epic:
                raise InitiativeLoadError("Each epic entry must be an object with a 'key'")
            key = epic["key"]
            if not isinstance(key, str):
                raise InitiativeLoadError("Epic key values must be strings")

    return content


def _data_dir() -> Path:
    path = Path(os.getenv("TEAM_BEACON_DATA_DIR", "./data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_path(filename: str | os.PathLike) -> Path:
    path = Path(filename)
    if path.is_absolute():
        return path
    return _data_dir() / path


def _config_dir() -> Path:
    return Path(os.getenv("TEAM_BEACON_CONFIG_DIR", "./config"))


def _resolve_initiatives_path(filename: str | os.PathLike) -> Path:
    path = Path(filename)
    if path.is_absolute():
        return path
    return _config_dir() / path


def write_dataset_to_csv(dataset: list[Mapping], filename: str | os.PathLike) -> None:
    filepath = resolve_path(filename)
    if not dataset:
        filepath.write_text("")
        return

    fieldnames = list(dataset[0].keys())
    with filepath.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in dataset:
            writer.writerow(row)


def write_dataset_to_json(data, filename: str | os.PathLike) -> bool:
    filepath = resolve_path(filename)
    try:
        with filepath.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4, default=str, ensure_ascii=False)
        return True
    except Exception as exc:  # pragma: no cover - IO edge case
        print(f"Error saving JSON: {exc}")
        return False


def load_initiatives(filename: str | os.PathLike = "initiatives.json") -> list[dict]:
    """Load and validate the initiatives structure from disk."""

    return _load_and_validate_initiatives(_resolve_initiatives_path(filename))


def load_epic_keys_from_initiatives(
    filename: str | os.PathLike = "initiatives.json",
) -> list[str]:
    """Return epic keys from an initiatives JSON file."""

    content = _load_and_validate_initiatives(_resolve_initiatives_path(filename))

    epic_keys: list[str] = []
    for group in content:
        epics = group.get("epics", [])
        for epic in epics:
            key = epic["key"]
            if key not in epic_keys:
                epic_keys.append(key)

    if not epic_keys:
        raise InitiativeLoadError("No epic keys found in initiatives file")

    return epic_keys


def merge_initiatives_with_epic_metrics(
    initiatives: Iterable[Mapping],
    epic_dataset: Iterable[Mapping],
) -> list[dict]:
    """Return a deep-copied initiatives structure enriched with epic metrics."""

    epic_by_key = {}
    for entry in epic_dataset:
        key = entry.get("issue_number")
        if not key:
            continue
        epic_by_key[key] = entry

    enriched_groups: list[dict] = []

    for group in initiatives:
        group_copy = {k: deepcopy(v) for k, v in group.items() if k != "epics"}
        group_epics = []
        for epic in group.get("epics", []):
            epic_copy = dict(epic)
            epic_key = epic_copy.get("key")
            metrics = epic_by_key.get(epic_key)
            if metrics:
                epic_copy.update(
                    {
                        "issue_number": metrics.get("issue_number", epic_key),
                        "title": metrics.get("title"),
                        "link": metrics.get("link"),
                        "total": metrics.get("total_issues"),
                        "total_issues": metrics.get("total_issues"),
                        "completed": metrics.get("completed"),
                        "inprogress": metrics.get("inprogress"),
                        "todo": metrics.get("todo"),
                        "percentage_done": metrics.get("percentage_done"),
                        "percentage_inprogress": metrics.get("percentage_inprogress"),
                        "percentage_todo": metrics.get("percentage_todo"),
                    }
                )
            group_epics.append(epic_copy)
        group_copy["epics"] = group_epics
        enriched_groups.append(group_copy)

    return enriched_groups
