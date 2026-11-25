"""Routing helpers (no Home Assistant required)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "c4_audio"))

from routing import (
    clamp_volume,
    displayed_source,
    enabled_indexes,
    ha_volume_to_percent,
    parse_zone_map,
    resolve_source_choice,
    split_names,
    volume_reading_is_stale,
)


def test_split_names_keeps_indexes():
    names = split_names("Kitchen\nDining\n\nMaster", 8, "Zone")
    assert names[0] == "Kitchen"
    assert names[2] == "Zone 3"
    assert names[3] == "Master"
    assert len(names) == 8


def test_skip_hyphen_zones():
    names = split_names("Kitchen\n-\nPatio", 3, "Zone")
    assert enabled_indexes(names) == [1, 3]


def test_clamp_volume_respects_software_cap():
    assert clamp_volume(80, 40) == 40
    assert clamp_volume(10, 40) == 10
    assert clamp_volume(-5, 100) == 0
    assert clamp_volume(120, 100) == 100


def test_volume_reading_hold_ignores_stale_jump():
    assert volume_reading_is_stale(now=10.0, commanded_at=9.0, commanded=10, decoded=100)
    assert not volume_reading_is_stale(now=10.0, commanded_at=9.0, commanded=10, decoded=12)
    assert not volume_reading_is_stale(now=13.0, commanded_at=9.0, commanded=10, decoded=100)
    assert not volume_reading_is_stale(now=10.0, commanded_at=None, commanded=None, decoded=100)


def test_ha_volume_slider_vs_percent_step():
    assert ha_volume_to_percent(1.0) == 100
    assert ha_volume_to_percent(0.1) == 10
    assert ha_volume_to_percent(1, as_percent=True) == 1
    assert ha_volume_to_percent(0, as_percent=True) == 0
    assert ha_volume_to_percent(12, as_percent=True) == 12
    assert ha_volume_to_percent(12) == 12


def test_empty_zone_name_is_skipped():
    assert enabled_indexes(["Kitchen", "", "Patio"]) == [1, 3]
    mapped = parse_zone_map({"1": {"name": "Kitchen"}, "2": {"name": ""}}, 3)
    assert mapped[1]["name"] == "Kitchen"
    assert mapped[2]["name"] == ""
    assert mapped[3]["name"] == ""


def test_zone_map_reads_turn_on_volume():
    mapped = parse_zone_map({"1": {"name": "a", "on_volume": 25}, "2": {"name": "b"}, "3": {"on_volume": "x"}}, 3)
    assert [mapped[n]["on_volume"] for n in (1, 2, 3)] == [25, None, None]


def test_select_source_maps_to_input():
    names = ["WiiM Pro", "-", "Tuner", "-", "-", "-", "-", "-"]
    assert resolve_source_choice("WiiM Pro", names) == 1
    assert resolve_source_choice("Tuner", names) == 3


def test_select_unknown_or_skipped_source_is_rejected():
    assert resolve_source_choice("Input 2", ["WiiM Pro", "-"]) == 2  # shown while routed there
    for name in ("Pandora", "-", "Input 9"):
        with pytest.raises(ValueError):
            resolve_source_choice(name, ["WiiM Pro", "-"])


def test_displayed_source():
    names = ["WiiM Pro", "-"]
    assert displayed_source(0, names) is None
    assert displayed_source(1, names) == "WiiM Pro"
    assert displayed_source(2, names) == "Input 2"
    assert displayed_source(5, names) == "Input 5"
