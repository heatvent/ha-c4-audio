# Changelog

Versions are integers: **1**, **2**, **3**, and so on. Each new release increments by one.

## [3]

- Zone setup uses a name field and an area dropdown per physical jack (Zone 1, Zone 2, …)
- Empty name skips that zone; Configure can add it later, or type `Zone 1` to use the jack as the name

## [2]

- Hardware picker lists three products: C4-AMP108-1B, C4-16AMP3-B, and C4-16ZAMSV3-B / AVM-16S1-B
- Removed the generic “16-zone amplifier” choice (that is not the 16×16 switch; a second speaker amp is a second integration entry)

## [1]

- HACS integration for Control4 Ethernet amps and the 16×16 audio switch
- Control4 brand icon and logo
- SDDP discovery and stable device identity (`c4.sy.info` / SDDP Host)
- Amp↔switch source carry-through
- Zone/source names, polling, bass/treble, `send_command` / `set_route` / `turn_off_all`

[3]: https://github.com/heatvent/ha-c4-audio/compare/v2...HEAD
[2]: https://github.com/heatvent/ha-c4-audio/compare/v1...v2
[1]: https://github.com/heatvent/ha-c4-audio/releases/tag/v1
