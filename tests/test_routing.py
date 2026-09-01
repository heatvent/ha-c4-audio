"""Routing helpers (no Home Assistant required)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "c4_audio"))

from routing import (
    KIND_LOCAL,
    KIND_SWITCH,
    clamp_volume,
    ha_volume_to_percent,
    displayed_amp_source,
    enabled_indexes,
    merged_source_list,
    parse_feeds,
    parse_zone_map,
    resolve_source_choice,
    split_names,
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


def test_parse_feeds_default_and_lines():
    assert parse_feeds("") == {1: 1}
    assert parse_feeds("1=1\n2=3") == {1: 1, 2: 3}


def test_select_wiim_goes_through_switch():
    amp = ["Switch feed", "Unused", "-", "-", "-", "-", "-", "-"]
    switch = ["EA-5", "-", "Retro Hi-Fi", "WiiM Pro"] + ["Input 5"] * 12
    kind, amp_in, sw_out, sw_in = resolve_source_choice(
        "WiiM Pro", amp, switch, {1: 1}
    )
    assert kind == KIND_SWITCH
    assert amp_in == 1
    assert sw_out == 1
    assert sw_in == 4


def test_select_local_amp_input():
    amp = ["Switch feed", "Tuner"]
    kind, amp_in, sw_out, sw_in = resolve_source_choice("Tuner", amp, ["WiiM Pro"], {1: 1})
    assert kind == KIND_LOCAL
    assert amp_in == 2
    assert sw_out is None


def test_merged_list_hides_switch_feed_jack():
    amp = ["Switch bus", "Tuner"]
    switch = ["WiiM Pro", "Pandora"]
    assert merged_source_list(amp, switch, {1: 1}) == ["WiiM Pro", "Pandora", "Tuner"]


def test_displayed_source_follows_switch():
    name = displayed_amp_source(1, ["Switch bus"], {1: 1}, 4, ["A", "B", "C", "WiiM Pro"])
    assert name == "WiiM Pro"
