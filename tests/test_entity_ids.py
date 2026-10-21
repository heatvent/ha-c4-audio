"""Unique-id migration (no Home Assistant required)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "c4_audio"))

from entity_ids import migrated_unique_id


def test_current_host_moves_to_ident():
    assert (
        migrated_unique_id(
            "192.168.68.93_zone_3",
            stable_id="c4-amp-serial",
            host="192.168.68.93",
        )
        == "c4-amp-serial_zone_3"
    )


def test_previous_dhcp_address_still_matches_known_suffix():
    assert (
        migrated_unique_id(
            "10.0.0.4_output_16_source",
            stable_id="c4-switch",
            host="10.0.0.9",
        )
        == "c4-switch_output_16_source"
    )


def test_already_stable_is_left_alone():
    assert (
        migrated_unique_id(
            "c4-amp-serial_all_zones",
            stable_id="c4-amp-serial",
            host="192.168.68.93",
        )
        is None
    )


def test_unrelated_id_is_left_alone():
    assert migrated_unique_id("something-else", stable_id="c4-amp", host="192.168.1.2") is None
