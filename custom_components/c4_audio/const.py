"""Constants for the Control4 Audio integration."""

DOMAIN = "c4_audio"
PLATFORMS = ["media_player", "number"]

DEFAULT_PORT = 8750
DEFAULT_POLL_INTERVAL = 15
DEFAULT_UDP_TIMEOUT = 1.5
DEFAULT_ON_VOLUME = 15
DEFAULT_SWITCH_ON_VOLUME = 100

CONF_MODEL = "model"
CONF_ZONE_NAMES = "zone_names"
CONF_SOURCE_NAMES = "source_names"
CONF_ON_VOLUME = "on_volume"
CONF_POLL_INTERVAL = "poll_interval"
CONF_UDP_TIMEOUT = "udp_timeout"
CONF_ENABLE_EQ = "enable_eq"
CONF_SWITCH_ENTRY_ID = "switch_entry_id"
CONF_SWITCH_FEEDS = "switch_feeds"
DEFAULT_SWITCH_FEEDS = "1=1"

# Serial-over-UDP framing used by C4 Ethernet audio hardware.
CMD_PREFIX_SET = "0s"
CMD_PREFIX_GET = "0g"
REPLY_PREFIX = "0r"
STATUS_PREFIX = "0t"

VOLUME_OFFSET = 155  # percent 0 → hex 9b

SKIP_NAME = "-"

MODEL_AMP108 = "c4_amp108_1b"
MODEL_AMP16 = "c4_16amp3_b"
MODEL_AMP16ZONE = "c4_amp_16z"
MODEL_MATRIX16 = "c4_16zamsv3_b"

MODELS = {
    MODEL_AMP108: {
        "name": "C4-AMP108-1B (4-zone amp)",
        "zones": 4,
        "inputs": 8,
        "kind": "amplifier",
        "cmd_ns": "c4.amp",
        "volume_mode": "offset",
        "volume_set": "chvol",
        "wake_power_save": True,
    },
    MODEL_AMP16: {
        "name": "C4-16AMP3-B (8-zone amp)",
        "zones": 8,
        "inputs": 8,
        "kind": "amplifier",
        "cmd_ns": "c4.amp",
        "volume_mode": "offset",
        "volume_set": "chvol",
        "wake_power_save": False,
    },
    MODEL_AMP16ZONE: {
        "name": "16-zone amplifier (c4.amp)",
        "zones": 16,
        "inputs": 8,
        "kind": "amplifier",
        "cmd_ns": "c4.amp",
        "volume_mode": "offset",
        "volume_set": "chvol",
        "wake_power_save": False,
    },
    MODEL_MATRIX16: {
        "name": "AVM-16S1-B / C4-16ZAMSV3-B (16x16 switch)",
        "zones": 16,
        "inputs": 16,
        "kind": "matrix",
        "cmd_ns": "c4.asw",
        "volume_mode": "percent_hex",
        "volume_set": "vol",
        "wake_power_save": False,
    },
}
