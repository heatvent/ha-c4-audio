# Home Assistant music dashboard

WiiM is the player (art, play/pause, skip, browse). Control4 Audio zones are the speakers (on/off and volume). Do not put play/pause on the amp entities — they have no transport.

1. Copy `scripts.yaml` into HA (or recreate the two scripts in Helpers).
2. Copy the view in `music.yaml` into a sections dashboard (raw YAML).
3. Fix entity IDs and the source string `WiiM Pro`.

Turn a single room on from its tile. **All On** routes every named zone to WiiM. **All Off** disconnects the amp zones and turns the WiiM off. Use the **5 Star** preset (or another WiiM preset) for playlists.
