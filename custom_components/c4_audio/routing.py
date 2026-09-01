"""Zone/source name parsing and amp↔switch carry-through."""

from __future__ import annotations

try:
    from .const import SKIP_NAME
except ImportError:  # running tests without the HA package
    from const import SKIP_NAME  # type: ignore

KIND_LOCAL = "local"
KIND_SWITCH = "switch"


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


def parse_zone_map(
    raw: dict | list | None,
    count: int,
    legacy_lines: str | None = None,
) -> dict[int, dict[str, str | None]]:
    """Map physical jack 1..N to {name, area_id}. Empty name means skip entity."""
    result: dict[int, dict[str, str | None]] = {
        index: {"name": "", "area_id": None} for index in range(1, count + 1)
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


def parse_feeds(text: str | None) -> dict[int, int]:
    """Parse `amp_input=switch_output` lines. Default bus is amp in 1 ← switch out 1."""
    feeds: dict[int, int] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        try:
            amp_input = int(left.strip(), 0)
            switch_output = int(right.strip(), 0)
        except ValueError:
            continue
        if amp_input < 1 or switch_output < 1:
            continue
        feeds[amp_input] = switch_output
    return feeds or {1: 1}


def name_index(names: list[str], source_name: str) -> int | None:
    try:
        return names.index(source_name) + 1
    except ValueError:
        return None


def resolve_source_choice(
    source_name: str,
    amp_source_names: list[str],
    switch_source_names: list[str] | None,
    feeds: dict[int, int],
) -> tuple[str, int, int | None, int | None]:
    """Map a UI source name to hardware jacks.

    Returns (kind, amp_input, switch_output, switch_input).
    Switch sources win when the same label exists on both chassis.
    """
    switch_names = switch_source_names or []
    switch_input = name_index(switch_names, source_name)
    if switch_input is not None and source_name != SKIP_NAME:
        amp_input, switch_output = next(iter(feeds.items()))
        return KIND_SWITCH, amp_input, switch_output, switch_input

    amp_input = name_index(amp_source_names, source_name)
    if amp_input is None or source_name == SKIP_NAME:
        raise ValueError(source_name)
    return KIND_LOCAL, amp_input, None, None


def merged_source_list(
    amp_source_names: list[str],
    switch_source_names: list[str] | None,
    feeds: dict[int, int],
) -> list[str]:
    """Sources shown on an amp zone: matrix inputs first, then local amp jacks."""
    fed_amp_inputs = set(feeds)
    local = [
        name
        for index, name in enumerate(amp_source_names)
        if name != SKIP_NAME and (index + 1) not in fed_amp_inputs
    ]
    matrix = visible_names(switch_source_names or [])
    seen: set[str] = set()
    merged: list[str] = []
    for name in matrix + local:
        if name in seen:
            continue
        seen.add(name)
        merged.append(name)
    return merged


def displayed_amp_source(
    amp_input: int,
    amp_source_names: list[str],
    feeds: dict[int, int],
    switch_output_source: int | None,
    switch_source_names: list[str] | None,
) -> str | None:
    """Friendly name for what an amp zone is actually playing."""
    if amp_input <= 0:
        return None
    if amp_input in feeds and switch_source_names is not None:
        if switch_output_source and switch_output_source > 0:
            names = switch_source_names
            if switch_output_source <= len(names):
                name = names[switch_output_source - 1]
                if name != SKIP_NAME:
                    return name
            return f"Input {switch_output_source}"
        return None
    if amp_input <= len(amp_source_names):
        name = amp_source_names[amp_input - 1]
        if name != SKIP_NAME:
            return name
    return f"Input {amp_input}"
