# Home Assistant music dashboard

WiiM is the player (art, play/pause, skip, browse). Control4 Audio zones are the speakers (on/off and volume). Do not put play/pause on the amp entities — they have no transport.

1. Copy `scripts.yaml` into HA if All Off should also stop the WiiM (the amp service does not).
2. Copy the view in `music.yaml` into a sections dashboard (raw YAML).
3. Fix entity IDs and the source string `WiiM Pro`.

Turn a single room on from its tile. **All On** calls `c4_audio.turn_on_all` (already-on rooms keep volume). **All Off** calls `c4_audio.turn_off_all` and then turns the WiiM off. Use **WiiM Pro** (or a preset) to pick the source.

After 1.0.6, add a live UDP log (entity ID from the amp device page):

```yaml
type: markdown
title: Log
card_mod:
  style: |
    ha-card {
      max-height: 12em;
      overflow-y: auto;
    }
content: |
  {% set log = state_attr('sensor.media_closet_control4_amp_udp_activity', 'activity') %}
  ```
  {% if log %}{{ log.split('\n')[-20:] | join('\n') }}{% else %}idle{% endif %}
  ```
```
