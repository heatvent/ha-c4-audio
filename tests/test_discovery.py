"""SDDP parsing tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "c4_audio"))

from const import MODEL_AMP16, MODEL_MATRIX16
from discovery import identity_from_info, parse_sddp_packet, suggest_model


def test_parse_amp_sddp():
    packet = (
        'NOTIFY ALIVE SDDP/1.0\r\n'
        'From: "192.168.68.93:1902"\r\n'
        'Host: "c4-16amp3-b-000fffabcdef"\r\n'
        'Type: "c4:v3_16chanamp:c4-16amp3-B"\r\n'
        'Manufacturer: "Control4"\r\n'
        'Model: "C4-16AMP3-B"\r\n'
        "\r\n"
    )
    device = parse_sddp_packet(packet)
    assert device is not None
    assert device.host == "192.168.68.93"
    assert device.ident == "c4-16amp3-b-000fffabcdef"
    assert device.suggested_model == MODEL_AMP16


def test_parse_switch_sddp():
    packet = (
        'NOTIFY ALIVE SDDP/1.0\r\n'
        'From: "192.168.68.80:1902"\r\n'
        'Host: "avm-16s1-b-000fff123456"\r\n'
        'Type: "c4:v3_avswitch:avm-16s1-b"\r\n'
        'Model: "AVM-16S1-B"\r\n'
        "\r\n"
    )
    device = parse_sddp_packet(packet)
    assert device is not None
    assert device.suggested_model == MODEL_MATRIX16


def test_skip_non_c4_audio():
    sony = (
        'NOTIFY ALIVE SDDP/1.0\r\n'
        'From: "192.168.68.98:1902"\r\n'
        'Host: "str-az1000es"\r\n'
        'Type: "c4:sony_receiver"\r\n'
        'Manufacturer: "Sony"\r\n'
        'Model: "STR-AZ1000ES"\r\n'
        "\r\n"
    )
    wiim = (
        'NOTIFY ALIVE SDDP/1.0\r\n'
        'From: "192.168.68.106:1902"\r\n'
        'Host: "wiim-pro"\r\n'
        'Type: "c4:wiim"\r\n'
        'Model: "WiiM Pro"\r\n'
        "\r\n"
    )
    assert parse_sddp_packet(sony) is None
    assert parse_sddp_packet(wiim) is None


def test_skip_ea5():
    packet = (
        'NOTIFY ALIVE SDDP/1.0\r\n'
        'From: "192.168.68.117:1902"\r\n'
        'Host: "ea5-000fff999999"\r\n'
        'Type: "c4:control4_ea5"\r\n'
        'Model: "EA-5"\r\n'
        "\r\n"
    )
    assert parse_sddp_packet(packet) is None


def test_identity_prefers_info_string():
    assert identity_from_info('v3_16chanamp:c4-16amp3-b:abc', "192.168.68.93") == (
        "v3_16chanamp:c4-16amp3-b:abc"
    )
    assert identity_from_info(None, "192.168.68.93") == "192.168.68.93"


def test_suggest_model_amp108():
    assert suggest_model("c4:c4amp", "C4-AMP108-1B", "amp108") is not None
