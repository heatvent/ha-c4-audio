"""Zone and source name parsing."""

from __future__ import annotations

from typing import Any

try:
    from .const import SKIP_NAME
except ImportError:  # running tests without the HA package
    from const import SKIP_NAME  # type: ignore


def split_names(value: str | list | None, count: int, prefix: str) -> list[str]:
    """One physical jack per line. Keep blank lines so indexes stay aligned."""
    if isinstance(value, list):
        lines = [str(item).rstrip() for item in value]
    else:
        lines = (value or "").splitlines()
    names: list[str] = []
    for index in range(count):
        if index < len(lines) and lines[index].strip():
            names.append(lines[index].strip())
        else:
            names.append(f"{prefix} {index + 1}")
    return names


def enabled_indexes(names: list[str]) -> list[int]:
    """1-based jack indexes that should get Home Assistant entities."""
    return [
        index + 1
        for index, name in enumerate(names)
        if name.strip() and name != SKIP_NAME
    ]


def _volume_or_none(value: Any) -> int | None:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return None


def parse_zone_map(
    raw: dict | list | None,
    count: int,
    legacy_lines: str | None = None,
) -> dict[int, dict[str, Any]]:
    """Map physical jack 1..N to {name, area_id, on_volume}. Empty name means skip entity."""
    result: dict[int, dict[str, Any]] = {
        index: {"name": "", "area_id": None, "on_volume": None} for index in range(1, count + 1)
    }
    if isinstance(raw, dict) and raw:
        for key, value in raw.items():
            try:
                index = int(key)
            except (TypeError, ValueError):
                continue
            if index not in result:
                continue
            if isinstance(value, dict):
                result[index] = {
                    "name": str(value.get("name") or "").strip(),
                    "area_id": value.get("area_id") or None,
                    "on_volume": _volume_or_none(value.get("on_volume")),
                }
            elif value:
                result[index]["name"] = str(value).strip()
        return result
    if legacy_lines:
        names = split_names(legacy_lines, count, "Zone")
        for index, name in enumerate(names, start=1):
            result[index]["name"] = "" if name == SKIP_NAME else name
    return result


def visible_names(names: list[str]) -> list[str]:
    return [name for name in names if name != SKIP_NAME]


def volume_reading_is_stale(
    *,
    now: float,
    commanded_at: float | None,
    commanded: int | None,
    decoded: int,
    hold_s: float = 2.5,
    threshold: int = 5,
) -> bool:
    """True when a fresh reading still shows the pre-command volume."""
    if commanded_at is None or commanded is None:
        return False
    return (now - commanded_at) < hold_s and abs(decoded - commanded) >= threshold


def clamp_volume(percent: int, max_volume: int) -> int:
    """Keep a 0–100 volume at or below the software cap. Never send chvolmax."""
    cap = max(0, min(100, int(max_volume)))
    return max(0, min(cap, int(percent)))


def ha_volume_to_percent(volume: float, *, as_percent: bool = False) -> int:
    """Map a Home Assistant slider (0–1) or a 0–100 step to percent.

    Slider 1.0 is 100%. Integer 1 from volume_up must stay 1%, not 100%.
    """
    if as_percent or volume > 1:
        return int(round(volume))
    return int(round(float(volume) * 100))


def name_index(names: list[str], source_name: str) -> int | None:
    try:
        return names.index(source_name) + 1
    except ValueError:
        return None


def resolve_source_choice(source_name: str, source_names: list[str]) -> int:
    """Map a UI source name to the physical input (1-based)."""
    if source_name != SKIP_NAME:
        index = name_index(source_names, source_name)
        if index is not None:
            return index
        # An unnamed input is shown as "Input N" while a zone is routed to it.
        for number, name in enumerate(source_names, start=1):
            if name == SKIP_NAME and source_name == f"Input {number}":
                return number
    raise ValueError(source_name)


def displayed_source(source: int, source_names: list[str]) -> str | None:
    """Friendly name for the input a zone is routed to."""
    if source <= 0:
        return None
    if source <= len(source_names):
        name = source_names[source - 1]
        if name != SKIP_NAME:
            return name
    return f"Input {source}"
