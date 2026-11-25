"""Constants for the Control4 Audio integration."""

DOMAIN = "c4_audio"
PLATFORMS = ["media_player", "number", "select", "sensor", "switch", "button"]

# Fired when a zone changed and Home Assistant did not ask for it (Control4, keypad, ...).
EVENT_EXTERNAL_CHANGE = "c4_audio_external_change"

DEFAULT_PORT = 8750
DEFAULT_POLL_INTERVAL = 15
DEFAULT_ACTIVE_POLL_INTERVAL = 5
DEFAULT_UDP_TIMEOUT = 1.5
DEFAULT_ON_VOLUME = 10
DEFAULT_MAX_VOLUME = 100

CONF_MODEL = "model"
CONF_ZONE_NAMES = "zone_names"
CONF_ZONES = "zones"
CONF_SOURCE_NAMES = "source_names"
CONF_ON_VOLUME = "on_volume"
CONF_MAX_VOLUME = "max_volume"
CONF_POLL_INTERVAL = "poll_interval"
CONF_ACTIVE_POLL_INTERVAL = "active_poll_interval"
CONF_UDP_TIMEOUT = "udp_timeout"
CONF_ENABLE_EQ = "enable_eq"
CONF_REMEMBER_SOURCE = "remember_source"
CONF_EXPERIMENTAL = "experimental_controls"
CONF_IDENT = "ident"

# Amp options from the audio switch support dropped after 1.0.13; migration strips them.
REMOVED_OPTIONS = ("switch_entry_id", "switch_feeds")

# Extra tries after a lost reply. Every GET, and every SET sent here, is safe to repeat.
GET_RETRIES = 2
SET_RETRIES = 1
# Polls in a row that must fail before the chassis is marked unavailable.
MAX_FAILED_POLLS = 3
# Zones in a row that must fail before All on / All off gives up on the chassis.
MAX_FAILED_ZONES = 2

# Control4's own driver sends at most one volume step per 250 ms (throttled_vol_ms_rate).
VOLUME_INTERVAL_S = 0.25

BALANCE_LIMIT = 10
INPUT_GAIN_LIMIT = 6  # lowest level is minus this; the highest is per model

# Serial-over-UDP framing used by C4 Ethernet audio hardware.
CMD_PREFIX_SET = "0s"
CMD_PREFIX_GET = "0g"
REPLY_PREFIX = "0r"
STATUS_PREFIX = "0t"
REJECTED = ("n01", "e00")

VOLUME_OFFSET = 155  # percent 0 → hex 9b

SKIP_NAME = "-"

MODEL_8AMP1 = "c4_8amp1_b"
MODEL_AMP108 = "c4_amp108_1b"
MODEL_AMP16 = "c4_16amp3_b"

MODELS = {
    MODEL_AMP16: {
        "name": "C4-16AMP3-B (8-zone speaker amp)",
        "default_title": "Control4 8-Zone Amp",
        "zones": 8,
        "inputs": 8,
        "wake_power_save": False,
        "digital_inputs": False,
        "input_gain_max": INPUT_GAIN_LIMIT,
    },
    MODEL_8AMP1: {
        "name": "C4-8AMP1-B (4-zone amp)",
        "default_title": "Control4 4-Zone Amp",
        "zones": 4,
        "inputs": 4,
        "wake_power_save": True,
        "digital_inputs": True,
        # Firmware 03.24.45 keeps a positive level at 0.
        "input_gain_max": 0,
    },
    MODEL_AMP108: {
        "name": "C4-AMP108-1B (4-zone amp)",
        "default_title": "Control4 4-Zone Amp",
        "zones": 4,
        "inputs": 8,
        "wake_power_save": True,
        "digital_inputs": True,
        "input_gain_max": 0,
    },
}
