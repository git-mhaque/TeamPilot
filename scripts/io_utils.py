"""Shared file IO helpers."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Iterable, Mapping


class InitiativeLoadError(RuntimeError):
    """Raised when initiatives.json cannot be parsed into epic keys."""


def _data_dir() -> Path:
    path = Path(os.getenv("TEAM_BEACON_DATA_DIR", "./data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_path(filename: str | os.PathLike) -> Path:
    path = Path(filename)
    if path.is_absolute():
        return path
    return _data_dir() / path


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


def load_epic_keys_from_initiatives(
    filename: str | os.PathLike = "initiatives.json",
) -> list[str]:
    """Return epic keys from an initiatives JSON file."""

    path = resolve_path(filename)
    try:
        with path.open("r", encoding="utf-8") as fh:
            content = json.load(fh)
    except FileNotFoundError as exc:  # pragma: no cover - direct failure path
        raise FileNotFoundError(f"Initiatives file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InitiativeLoadError(f"Initiatives file is not valid JSON: {path}") from exc

    if not isinstance(content, list):
        raise InitiativeLoadError("Initiatives file must contain a list of groups")

    epic_keys: list[str] = []
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
            if key not in epic_keys:
                epic_keys.append(key)

    if not epic_keys:
        raise InitiativeLoadError("No epic keys found in initiatives file")

    return epic_keys
