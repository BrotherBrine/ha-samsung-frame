"""Constants for the Samsung Frame TV integration."""

from __future__ import annotations

DOMAIN = "samsung_frame"

CONF_TOKEN = "token"
CONF_MAC = "mac"
CONF_MODEL = "model"
CONF_APPS = "apps"
CONF_INPUTS = "inputs"
CONF_SMARTTHINGS_ENTITY = "smartthings_entity"

# After picking an input, trust our own choice this long before SmartThings catches up
INPUT_COMMAND_GRACE_SECONDS = 15

# SmartThings source names that mean the built-in tuner
TUNER_SOURCE_ALIASES = {"tv", "dtv", "digitaltv", "antenna", "cable", "livetv"}

SCAN_INTERVAL_SECONDS = 10

CARD_URL = "/samsung_frame/frame-tv-card.js"
CARD_VERSION = "1.0.0"

# Input name -> remote key
DEFAULT_INPUTS = "TV: KEY_TV\nHDMI 1: KEY_HDMI1\nHDMI 2: KEY_HDMI2\nHDMI 3: KEY_HDMI3"

# App name -> Tizen app id (append ", native" to a line to use NATIVE_LAUNCH)
DEFAULT_APPS = "\n".join(
    [
        "Netflix: 3201907018807",
        "YouTube: 111299001912",
        "Prime Video: 3201910019365",
        "Disney+: 3201901017640",
        "Hulu: 3201601007625",
        "Max: 3202301029760",
        "Apple TV: 3201807016597",
        "Plex: 3201512006963",
        "Spotify: 3201606009684",
    ]
)


def parse_mapping(text: str) -> dict[str, tuple[str, bool]]:
    """Parse 'Name: value[, native]' lines into {name: (value, native)}."""
    result: dict[str, tuple[str, bool]] = {}
    for line in (text or "").splitlines():
        name, sep, value = line.rpartition(":")
        if not sep or not name.strip() or not value.strip():
            continue
        parts = [p.strip() for p in value.split(",")]
        result[name.strip()] = (parts[0], "native" in (p.lower() for p in parts[1:]))
    return result
