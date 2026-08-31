# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2026-08-31

### Added

- SDDP discovery (UDP 1902) so amps and switches can be picked from a list instead of typing IPs
- Stable unique id from `c4.sy.info` / SDDP Host (MAC-style identity) so DHCP IP changes stay linked
- DHCP discovery for Control4 MAC OUI `00:0F:FF`, ignored unless the chassis answers as an amp or switch on UDP 8750

## [0.2.1] - 2026-08-31

### Added

- Control4 brand icon and logo (Home Assistant `brand/` assets plus HACS repo `brand/` copies)
- This changelog

## [0.2.0] - 2026-08-31

### Added

- HACS custom integration for Control4 Ethernet amps and the AVM-16S1-B / C4-16ZAMSV3-B switch
- One config entry per chassis (8-zone, 16-zone, AMP108, or 16×16 switch)
- Amp↔switch source carry-through (`amp_input=switch_output` feed map)
- Zone/source names with `-` to skip unused jacks
- Media players: route, mute, volume, volume step
- Optional amp bass/treble number entities
- Status polling (default 15s) plus refresh after SET
- Services: `send_command`, `set_route`, `turn_off_all`

### Notes

- Amp volume is percent + 155 (`c4.amp.chvol`). Switch line gain is 0–100 hex (`c4.asw.vol`, `64` = unity)
- `c4.amp.chvolmax` is not used (firmware volume jump)
- `c4.amp.psave` is only sent on AMP108; 16AMP3 returns `n01`

[0.2.1]: https://github.com/heatvent/ha-c4-audio/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/heatvent/ha-c4-audio/releases/tag/v0.2.0
