"""Behavior against a fake amp: lost replies, outside changes, setup, entities, services."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.c4_audio.const import (
    DOMAIN,
    EVENT_EXTERNAL_CHANGE,
    MODEL_8AMP1,
    MODEL_AMP16,
    MODEL_AMP108,
    MODELS,
)
from custom_components.c4_audio.diagnostics import async_get_config_entry_diagnostics
from custom_components.c4_audio.protocol import ParsedPacket
from custom_components.c4_audio.udp_client import C4UdpClient, ProbeIdentity

CLIENT = "custom_components.c4_audio.udp_client.C4UdpClient."
FLOW = "custom_components.c4_audio.config_flow."


@pytest.fixture(autouse=True)
def _storage(hass_storage, enable_custom_integrations):
    """Keep the last-source store in memory."""


class FakeAmp:
    """Answers like a C4-16AMP3-B. `lose` decides which commands get no reply."""

    def __init__(self, zones: int = 8) -> None:
        self.out = [0] * zones
        self.vol = [10] * zones
        self.mute = [1] * zones
        self.bal = [0] * zones
        self.gain = [0] * 9
        self.ignore: tuple[str, ...] = ()
        self.lose = lambda body: False
        self.sent: list[str] = []

    async def send(self, _client, prefix, body, *, retries=0):
        for _attempt in range(retries + 1):
            self.sent.append(body)
            if not self.lose(body):
                return self._answer(prefix, body)
        return None

    def _answer(self, prefix, body):
        name, *args = body.split()
        if prefix == "0g":
            if name == "c4.sy.fwv":
                return ParsedPacket("reply", 1, "000", name, ['"1.2.3"'], body)
            if name == "c4.amp.igain":
                n = int(args[0], 16)
                return ParsedPacket("reply", 1, "000", name, [args[0], f"{self.gain[n] & 255:02x}"], body)
            lists = {
                "c4.amp.ain": self.out,
                "c4.amp.avol": [v + 155 for v in self.vol],
                "c4.amp.amut": self.mute,
                "c4.amp.abal": [v & 255 for v in self.bal],
                "c4.amp.abss": [0] * len(self.out),
                "c4.amp.atrb": [0] * len(self.out),
            }
            if name not in lists:
                return ParsedPacket("reply", 1, "n01", None, [], body)
            return ParsedPacket("reply", 1, "000", name, [f"{v:02x}" for v in lists[name]], body)
        if not name.startswith(self.ignore or ("\0",)):
            index, value = (int(a, 16) for a in args) if len(args) == 2 else (0, 0)
            if name == "c4.amp.out":
                self.out[index - 1] = value
            elif name == "c4.amp.mute":
                self.mute[index - 1] = value
            elif name == "c4.amp.chvol":
                self.vol[index - 1] = value - 155
            elif name == "c4.amp.bal":
                self.bal[index - 1] = value - 256 if value > 127 else value
            elif name == "c4.amp.igain":
                self.gain[index] = value - 256 if value > 127 else value
        return ParsedPacket("reply", 1, "000", None, [], body)


@pytest.fixture
def amp():
    amp = FakeAmp()
    with (
        patch(CLIENT + "async_start", AsyncMock()),
        patch(CLIENT + "async_stop", AsyncMock()),
        patch(CLIENT + "async_send", lambda *a, **k: amp.send(*a, **k)),
    ):
        yield amp


def make_entry(hass: HomeAssistant, *, model=MODEL_AMP16, ident="amp", options=None, zones=None, sources=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Amp",
        unique_id=ident,
        minor_version=2,
        data={
            "host": "192.0.2.1",
            "port": 8750,
            "model": model,
            "ident": ident,
            "zones": zones or {"1": {"name": "Kitchen"}, "2": {"name": "Bar"}, "3": {"name": "Patio"}},
            "source_names": sources or "WiiM Pro\nTuner\n" + "\n".join(["-"] * (MODELS[model]["inputs"] - 2)),
        },
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


async def setup(hass: HomeAssistant, **kwargs) -> MockConfigEntry:
    entry = make_entry(hass, **kwargs)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity(hass: HomeAssistant, domain: str, suffix: str, ident="amp") -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{ident}_{suffix}")
    assert entity_id, suffix
    return entity_id


# ----------------------------------------------------------------- reliability


async def test_one_lost_reply_is_retried(hass: HomeAssistant, amp: FakeAmp) -> None:
    entry = await setup(hass)
    left = [1]

    def lose(body):
        if body == "c4.amp.ain" and left:
            left.pop()
            return True
        return False

    amp.lose = lose
    await entry.runtime_data.async_refresh()
    assert not left
    assert entry.runtime_data._failed_polls == 0


async def test_unavailable_only_after_three_missed_polls(hass: HomeAssistant, amp: FakeAmp) -> None:
    amp.out[0], amp.mute[0] = 1, 0
    entry = await setup(hass)
    kitchen = entity(hass, "media_player", "zone_1")
    amp.lose = lambda body: True
    for expected in ("on", "on", "unavailable"):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(kitchen).state == expected
    amp.lose = lambda body: False
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(kitchen).state == "on"
    # The count starts over after a good poll.
    amp.lose = lambda body: True
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(kitchen).state == "on"


@pytest.mark.parametrize("failure", ["silent", "oserror"])
async def test_unreachable_at_startup_retries_setup(hass: HomeAssistant, amp: FakeAmp, failure) -> None:
    entry = make_entry(hass)
    if failure == "silent":
        amp.lose = lambda body: True
        await hass.config_entries.async_setup(entry.entry_id)
    else:
        with patch(CLIENT + "async_start", AsyncMock(side_effect=OSError("unreachable"))):
            await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_all_off_continues_past_one_failed_zone(hass: HomeAssistant, amp: FakeAmp) -> None:
    amp.out[:3] = [1, 1, 1]
    entry = await setup(hass)
    amp.lose = lambda body: body == "c4.amp.mute 01 01"
    with pytest.raises(HomeAssistantError, match="Kitchen"):
        await entry.runtime_data.async_turn_off_all()
    assert amp.out[:3] == [1, 0, 0]
    await hass.async_block_till_done()


async def test_all_off_gives_up_on_a_dead_amp(hass: HomeAssistant, amp: FakeAmp) -> None:
    amp.out[:3] = [1, 1, 1]
    entry = await setup(hass)
    amp.lose = lambda body: True
    amp.sent.clear()
    with pytest.raises(HomeAssistantError, match="Kitchen, Bar, Patio"):
        await entry.runtime_data.async_turn_off_all()
    assert not any(body.startswith("c4.amp.mute 03") for body in amp.sent)
    await hass.async_block_till_done()


async def test_rejected_command_is_an_error(hass: HomeAssistant, amp: FakeAmp) -> None:
    entry = await setup(hass)
    with patch.object(
        entry.runtime_data.client,
        "async_send",
        AsyncMock(return_value=ParsedPacket("reply", 1, "e00", None, [], "")),
    ), pytest.raises(HomeAssistantError, match="rejected"):
        await entry.runtime_data.async_set_mute(1, True)
    assert entry.runtime_data.state.zones[1].muted is True  # unchanged: the fake amp starts muted


async def test_retried_set_cannot_land_after_a_newer_command() -> None:
    """The lock is held across tries, so an old 'on' never follows a newer 'off'."""
    client = C4UdpClient("192.0.2.1", 8750, 0.01)
    order = []

    async def once(prefix, body):
        order.append(body)
        await asyncio.sleep(0.01)
        if body == "on" and order.count("on") < 2:
            return None
        return ParsedPacket("reply", 1, "000", None, [], "")

    client._async_send_locked = once
    await asyncio.gather(
        client.async_send("0s", "on", retries=1), client.async_send("0s", "off", retries=1)
    )
    assert order == ["on", "on", "off"]


async def test_closed_client_does_not_reopen() -> None:
    client = C4UdpClient("192.0.2.1", 8750, 0.01)
    await client.async_stop()
    with patch.object(client, "_open_socket", AsyncMock()) as opened:
        assert await client.async_send("0s", "x", retries=2) is None
    opened.assert_not_awaited()


# --------------------------------------------------------------------- polling


async def test_polls_faster_while_playing_but_slow_values_stay_slow(hass: HomeAssistant, amp: FakeAmp) -> None:
    entry = await setup(hass)
    coordinator = entry.runtime_data
    assert coordinator.update_interval.total_seconds() == 15
    amp.out[0] = 1
    amp.sent.clear()
    await coordinator.async_refresh()
    assert coordinator.update_interval.total_seconds() == 5
    assert amp.sent == ["c4.amp.ain", "c4.amp.avol", "c4.amp.amut"]
    coordinator._last_full_poll -= 15
    amp.sent.clear()
    await coordinator.async_refresh()
    assert {"c4.sy.fwv", "c4.amp.abss", "c4.amp.atrb"} <= set(amp.sent)
    amp.out[0] = 0
    await coordinator.async_refresh()
    assert coordinator.update_interval.total_seconds() == 15


# -------------------------------------------------------------- outside changes


async def test_outside_change_fires_an_event(hass: HomeAssistant, amp: FakeAmp) -> None:
    events = async_capture_events(hass, EVENT_EXTERNAL_CHANGE)
    entry = await setup(hass)
    assert events == []  # the first poll is the baseline
    amp.out[1], amp.mute[1] = 2, 0
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(events) == 1
    data = events[0].data
    assert data["entity_id"] == entity(hass, "media_player", "zone_2")
    assert data["zone_name"] == "Bar"
    assert data["changed"] == ["muted", "source"]
    assert data["previous"] == {"source": 0, "muted": True}
    assert data["source_name"] == "Tuner"


async def test_own_commands_fire_no_event(hass: HomeAssistant, amp: FakeAmp) -> None:
    events = async_capture_events(hass, EVENT_EXTERNAL_CHANGE)
    entry = await setup(hass)
    await entry.runtime_data.async_turn_on(1)
    await entry.runtime_data.async_set_volume(1, 0.3)
    await entry.runtime_data.async_select_source(1, "Tuner")
    await entry.runtime_data.async_turn_off(1)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert events == []


async def test_own_command_with_a_lost_reply_is_not_an_outside_change(hass: HomeAssistant, amp: FakeAmp) -> None:
    events = async_capture_events(hass, EVENT_EXTERNAL_CHANGE)
    entry = await setup(hass)
    amp.lose = lambda body: body == "c4.amp.out 01 01"
    with pytest.raises(HomeAssistantError):
        await entry.runtime_data.async_turn_on(1)
    amp.lose = lambda body: False
    amp.out[0] = 1  # the command did land
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert entry.runtime_data.zone_is_on(1)
    assert events == []


async def test_status_frame_reports_a_change(hass: HomeAssistant, amp: FakeAmp) -> None:
    events = async_capture_events(hass, EVENT_EXTERNAL_CHANGE)
    entry = await setup(hass)
    entry.runtime_data._on_packet(
        ParsedPacket("status", None, None, "c4.amp.out", ["03", "01"], "")
    )
    await hass.async_block_till_done()
    assert [e.data["zone_name"] for e in events] == ["Patio"]


async def test_select_shows_an_unnamed_input(hass: HomeAssistant, amp: FakeAmp) -> None:
    amp.out[0], amp.mute[0] = 5, 0
    entry = await setup(hass)
    select = entity(hass, "select", "zone_1_source")
    state = hass.states.get(select)
    assert state.state == "Input 5"
    assert state.attributes["options"] == ["Off", "WiiM Pro", "Tuner", "Input 5"]
    await hass.services.async_call("select", "select_option", {"entity_id": select, "option": "Input 5"}, blocking=True)
    assert amp.out[0] == 5
    await entry.runtime_data.async_turn_off(1)
    await hass.async_block_till_done()
    assert hass.states.get(select).state == "Off"


# -------------------------------------------------------------- volume, sources


async def test_fast_volume_drag_sends_only_the_latest(hass: HomeAssistant, amp: FakeAmp) -> None:
    amp.out[0], amp.mute[0] = 1, 0
    entry = await setup(hass)
    coordinator = entry.runtime_data
    amp.sent.clear()
    with patch("custom_components.c4_audio.coordinator.VOLUME_INTERVAL_S", 0.05):
        await asyncio.gather(*(coordinator.async_set_volume(1, v / 100) for v in range(20, 31)))
    sent = [body for body in amp.sent if "chvol" in body]
    assert len(sent) <= 3
    assert amp.vol[0] == 30


async def test_volume_waiting_in_line_does_not_wake_a_zone_turned_off(hass: HomeAssistant, amp: FakeAmp) -> None:
    amp.out[0], amp.mute[0] = 1, 0
    entry = await setup(hass)
    coordinator = entry.runtime_data
    with patch("custom_components.c4_audio.coordinator.VOLUME_INTERVAL_S", 0.05):
        await coordinator.async_set_volume(1, 0.2)
        waiting = asyncio.create_task(coordinator.async_set_volume(1, 0.5))
        await asyncio.sleep(0)
        await coordinator.async_turn_off(1)
        await waiting
    assert amp.out[0] == 0
    assert amp.mute[0] == 1
    assert amp.vol[0] == 20
    await hass.async_block_till_done()


async def test_old_volume_is_not_applied_after_off_and_on(hass: HomeAssistant, amp: FakeAmp) -> None:
    amp.out[0], amp.mute[0] = 1, 0
    entry = await setup(hass)
    coordinator = entry.runtime_data
    with patch("custom_components.c4_audio.coordinator.VOLUME_INTERVAL_S", 0.05):
        await coordinator.async_set_volume(1, 0.2)
        waiting = asyncio.create_task(coordinator.async_set_volume(1, 0.8))
        await asyncio.sleep(0)
        await coordinator.async_turn_off(1)
        await coordinator.async_turn_on(1)
        await waiting
    assert amp.vol[0] == 10
    await hass.async_block_till_done()


async def test_volume_steps_build_on_the_waiting_target(hass: HomeAssistant, amp: FakeAmp) -> None:
    amp.out[0], amp.mute[0], amp.vol[0] = 1, 0, 20
    entry = await setup(hass)
    with patch("custom_components.c4_audio.coordinator.VOLUME_INTERVAL_S", 0.02):
        await asyncio.gather(*(entry.runtime_data.async_adjust_volume(1, 1) for _ in range(5)))
    assert amp.vol[0] == 25


async def test_last_source_is_remembered_across_reload(hass: HomeAssistant, amp: FakeAmp) -> None:
    entry = await setup(hass)
    await entry.runtime_data.async_select_source(1, "Tuner")
    await entry.runtime_data.async_turn_off(1)
    await entry.runtime_data.async_turn_on(1)
    assert amp.out[0] == 2
    await entry.runtime_data.async_turn_off(1)
    await entry.runtime_data._store.async_save({"1": 2})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await entry.runtime_data.async_turn_on(1)
    assert amp.out[0] == 2
    await entry.runtime_data.async_turn_on(2)
    assert amp.out[1] == 1  # nothing remembered: first named input
    await hass.async_block_till_done()


async def test_unnamed_last_source_and_disabled_option_use_the_default(hass: HomeAssistant, amp: FakeAmp) -> None:
    amp.out[0] = 6  # Control4 used an input that has no name here
    entry = await setup(hass)
    await entry.runtime_data.async_turn_off(1)
    await entry.runtime_data.async_turn_on(1)
    assert amp.out[0] == 1
    hass.config_entries.async_update_entry(entry, options={"remember_source": False})
    await hass.async_block_till_done()
    await entry.runtime_data.async_select_source(1, "Tuner")
    await entry.runtime_data.async_turn_off(1)
    await entry.runtime_data.async_turn_on(1)
    assert amp.out[0] == 1
    await hass.async_block_till_done()


async def test_turn_on_volume_per_zone(hass: HomeAssistant, amp: FakeAmp) -> None:
    entry = await setup(
        hass,
        zones={"1": {"name": "Kitchen", "on_volume": 25}, "2": {"name": "Bar"}, "3": {"name": "Patio", "on_volume": 90}},
        options={"on_volume": 12, "max_volume": 60},
    )
    await entry.runtime_data.async_turn_on_all()
    assert amp.vol[:3] == [25, 12, 60]
    await hass.async_block_till_done()


# ---------------------------------------------------------------------- models


async def test_16amp3_skips_the_digital_check(hass: HomeAssistant, amp: FakeAmp) -> None:
    entry = await setup(hass)
    await entry.runtime_data.async_turn_on(1)
    assert not any("digi" in body or "psave" in body for body in amp.sent)
    await hass.async_block_till_done()


async def test_8amp1_has_four_zones_and_inputs(hass: HomeAssistant) -> None:
    amp = FakeAmp(4)
    # Losing the wake or the digital check must not stop the zone from turning on.
    amp.lose = lambda body: "psave" in body or "digi" in body
    with (
        patch(CLIENT + "async_start", AsyncMock()),
        patch(CLIENT + "async_stop", AsyncMock()),
        patch(CLIENT + "async_send", lambda *a, **k: amp.send(*a, **k)),
    ):
        entry = await setup(hass, model=MODEL_8AMP1)
        coordinator = entry.runtime_data
        assert (coordinator.zone_count, coordinator.input_count) == (4, 4)
        await coordinator.async_select_source(1, "Tuner")
        assert amp.out[0] == 2
        assert "c4.amp.psave 00" in amp.sent and "c4.amp.digi 02" in amp.sent
        with pytest.raises(HomeAssistantError):
            await coordinator.async_route_output(1, 5)
        with pytest.raises(HomeAssistantError):
            await coordinator.async_route_output(5, 1)
        await hass.async_block_till_done()


def test_supported_models() -> None:
    assert set(MODELS) == {MODEL_AMP16, MODEL_8AMP1, MODEL_AMP108}


async def test_removed_16_zone_profile_fails_clearly(hass: HomeAssistant, amp: FakeAmp) -> None:
    entry = MockConfigEntry(domain=DOMAIN, minor_version=2, data={"host": "x", "port": 1, "model": "c4_amp_16z"})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR


# ---------------------------------------------------------------- experimental


async def test_experimental_controls_are_off_by_default(hass: HomeAssistant, amp: FakeAmp) -> None:
    await setup(hass)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("number", DOMAIN, "amp_zone_1_balance") is None
    assert registry.async_get_entity_id("number", DOMAIN, "amp_input_1_gain") is None
    assert not any("abal" in body or "igain" in body for body in amp.sent)


async def test_balance_and_input_level(hass: HomeAssistant, amp: FakeAmp) -> None:
    entry = await setup(hass, options={"experimental_controls": True})
    coordinator = entry.runtime_data
    await coordinator.async_set_balance(1, -3)
    await coordinator.async_set_input_gain(1, -2)
    assert amp.bal[0] == -3 and amp.gain[1] == -2
    assert "c4.amp.bal 01 fd" in amp.sent and "c4.amp.igain 01 fe" in amp.sent
    assert hass.states.get(entity(hass, "number", "zone_1_balance")).state == "-3"
    assert hass.states.get(entity(hass, "number", "input_1_gain")).state == "-2"
    # The amp answers OK but does nothing: say so, and show the real value.
    amp.ignore = ("c4.amp.bal", "c4.amp.igain")
    with pytest.raises(HomeAssistantError, match="did not change"):
        await coordinator.async_set_balance(1, 4)
    with pytest.raises(HomeAssistantError, match="did not change"):
        await coordinator.async_set_input_gain(1, 4)
    assert coordinator.state.zones[1].balance == -3
    # Turning the option off removes them again, and nothing else.
    hass.config_entries.async_update_entry(entry, options={"experimental_controls": False})
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("number", DOMAIN, "amp_zone_1_balance") is None
    assert registry.async_get_entity_id("number", DOMAIN, "amp_input_1_gain") is None
    assert registry.async_get_entity_id("number", DOMAIN, "amp_zone_1_bass")


# -------------------------------------------------------------------- entities


async def test_controls_join_their_room_as_config_entities(hass: HomeAssistant, amp: FakeAmp) -> None:
    areas = ar.async_get(hass)
    kitchen, office = areas.async_create("Kitchen"), areas.async_create("Office")
    entry = make_entry(hass, zones={"1": {"name": "Kitchen", "area_id": kitchen.id}, "2": {"name": "Bar"}})
    registry = er.async_get(hass)
    kept = registry.async_get_or_create("number", DOMAIN, "amp_zone_1_bass", config_entry=entry)
    registry.async_update_entity(kept.entity_id, area_id=office.id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for domain, suffix in (("select", "zone_1_source"), ("number", "zone_1_treble")):
        found = registry.async_get(entity(hass, domain, suffix))
        assert found.area_id == kitchen.id
        assert found.entity_category is EntityCategory.CONFIG
    assert registry.async_get(kept.entity_id).area_id == office.id
    assert registry.async_get(entity(hass, "select", "zone_2_source")).area_id is None


async def test_cleared_zone_loses_its_entities_only(hass: HomeAssistant, amp: FakeAmp) -> None:
    entry = await setup(hass)
    registry = er.async_get(hass)
    before = {e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    hass.config_entries.async_update_entry(
        entry, options={"zones": {"1": {"name": "Kitchen"}, "2": {"name": ""}, "3": {"name": "Patio"}}}
    )
    await hass.async_block_till_done()
    after = {e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert before - after == {f"amp_zone_2{s}" for s in ("", "_source", "_bass", "_treble")}
    assert after <= before


async def test_activity_log_is_not_recorded(hass: HomeAssistant, amp: FakeAmp) -> None:
    await setup(hass)
    state = hass.states.get(entity(hass, "sensor", "udp_activity"))
    assert "activity" in state.state_info["unrecorded_attributes"]


async def test_diagnostics_hide_identity_and_work_unloaded(hass: HomeAssistant, amp: FakeAmp) -> None:
    ident = "v3_16chanamp:c4-16amp3-b:00:0f:ff:00:00:01"
    entry = make_entry(hass, ident=ident)
    assert "entry" in await async_get_config_entry_diagnostics(hass, entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entry.runtime_data.client._note("12:00:00  →  192.0.2.1  0s", noisy=True)
    text = str(await async_get_config_entry_diagnostics(hass, entry))
    assert ident not in text
    assert "192.0.2.1" not in text
    assert "Kitchen" in text


# -------------------------------------------------------------------- services


async def test_services_target_a_device(hass: HomeAssistant, amp: FakeAmp) -> None:
    entry = await setup(hass)
    other = make_entry(hass, ident="other")
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()
    device = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0]
    route = {"output": 1, "input": 2}
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "set_route", route, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "turn_off_all", {"device_id": "nope"}, blocking=True)
    await hass.services.async_call(DOMAIN, "set_route", {**route, "device_id": device.id}, blocking=True)
    assert entry.runtime_data.state.zones[1].source == 2
    assert other.runtime_data.state.zones[1].source == 0
    await hass.services.async_call(DOMAIN, "turn_off_all", {"host": "192.0.2.1"}, blocking=True)
    await hass.async_block_till_done()


async def test_one_amp_failing_does_not_stop_the_next(hass: HomeAssistant, amp: FakeAmp) -> None:
    first = await setup(hass)
    second = make_entry(hass, ident="other")
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    with (
        patch.object(first.runtime_data, "async_turn_off_all", AsyncMock(side_effect=HomeAssistantError("x"))),
        patch.object(second.runtime_data, "async_turn_off_all", AsyncMock()) as ok,
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(DOMAIN, "turn_off_all", {}, blocking=True)
    ok.assert_awaited_once()


# ----------------------------------------------------------------------- setup


def probe(identity):
    return patch(FLOW + "async_probe_identity", AsyncMock(return_value=identity))


async def test_dhcp_confirms_with_a_readable_name(hass: HomeAssistant, amp: FakeAmp) -> None:
    class Info:
        ip = "192.0.2.5"
        macaddress = "000fff000001"

    with probe(ProbeIdentity("1", "v1_8chanamp:c4-8amp1-b:x", MODEL_8AMP1)):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "dhcp"}, data=Info())
    assert result["step_id"] == "confirm"
    assert "C4-8AMP1-B" in result["description_placeholders"]["model"]
    flow = hass.config_entries.flow.async_progress()[0]
    assert flow["context"]["title_placeholders"]["name"] == "Control4 4-Zone Amp (192.0.2.5)"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Closet Amp"})
    assert result["step_id"] == "inputs"
    assert len(result["data_schema"].schema) == 4
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"input_1_name": "WiiM"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"zone_1_name": "Kitchen", "zone_1_volume": 22}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Closet Amp"
    assert result["data"]["zones"]["1"]["on_volume"] == 22
    await hass.async_block_till_done()


async def test_zone_fields_can_be_cleared(hass: HomeAssistant, amp: FakeAmp) -> None:
    entry = await setup(hass, zones={"1": {"name": "Kitchen", "on_volume": 25}, "2": {"name": "Bar"}})
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "outputs"})
    suggested = {str(k): k.description["suggested_value"] for k in form["data_schema"].schema if k.description}
    assert suggested == {"zone_1_name": "Kitchen", "zone_1_volume": 25, "zone_2_name": "Bar"}
    # The frontend leaves cleared fields out.
    await hass.config_entries.options.async_configure(form["flow_id"], {"zone_1_name": "Kitchen"})
    await hass.async_block_till_done()
    assert entry.runtime_data.enabled_zones == [1]
    assert entry.options["zones"]["1"]["on_volume"] is None


@pytest.mark.parametrize(
    ("identity", "outcome"),
    [
        (ProbeIdentity("1", "AMP", MODEL_AMP16), "reconfigure_successful"),
        (ProbeIdentity("1", "someone-else", MODEL_AMP16), "wrong_device"),
        (None, "cannot_connect"),
        (ProbeIdentity("1", "amp", None, not_amp=True), "not_an_amp"),
    ],
)
async def test_reconfigure(hass: HomeAssistant, amp: FakeAmp, identity, outcome) -> None:
    entry = await setup(hass)
    ids = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with probe(identity):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.0.2.99", "port": 8750}
        )
    await hass.async_block_till_done()
    if outcome in ("cannot_connect", "not_an_amp"):
        assert result["errors"] == {"base": outcome}
    else:
        assert result["reason"] == outcome
    moved = outcome == "reconfigure_successful"
    assert entry.data["host"] == ("192.0.2.99" if moved else "192.0.2.1")
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.host == entry.data["host"]
    assert ids == {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}


async def test_manual_setup_is_not_blocked_by_a_discovery_card(hass: HomeAssistant, amp: FakeAmp) -> None:
    class Info:
        ip = "192.0.2.5"
        macaddress = "000fff000001"

    found = ProbeIdentity("1", "v1_8chanamp:c4-8amp1-b:x", MODEL_8AMP1)
    with probe(found), patch(FLOW + "async_sddp_search", AsyncMock(return_value=[])):
        await hass.config_entries.flow.async_init(DOMAIN, context={"source": "dhcp"}, data=Info())
        flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"name": "Spare", "host": "192.0.2.5", "port": 8750, "model": MODEL_AMP16}
        )
    assert result["step_id"] == "inputs"
    assert len(result["data_schema"].schema) == 4  # detected, not the model picked in the form
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"input_1_name": "WiiM"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"zone_1_name": "Test"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.config_entries.flow.async_progress() == []  # the card is gone


async def test_zero_volume_stays_zero_when_the_amp_stores_one(hass: HomeAssistant, amp: FakeAmp) -> None:
    amp.out[0], amp.mute[0] = 1, 0
    events = async_capture_events(hass, EVENT_EXTERNAL_CHANGE)
    entry = await setup(hass)
    coordinator = entry.runtime_data
    await coordinator.async_set_volume(1, 0.0)
    amp.vol[0] = 1
    coordinator._commanded_at.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.state.zones[1].volume == 0
    assert events == []
    await coordinator.async_adjust_volume(1, 1)
    await coordinator.async_refresh()
    assert coordinator.state.zones[1].volume == 1  # a real 1% is still 1%


@pytest.mark.parametrize(("model", "highest"), [(MODEL_8AMP1, 0), (MODEL_AMP16, 6)])
async def test_input_level_range(hass: HomeAssistant, amp: FakeAmp, model, highest) -> None:
    await setup(hass, model=model, options={"experimental_controls": True})
    state = hass.states.get(entity(hass, "number", "input_1_gain"))
    assert (state.attributes["min"], state.attributes["max"]) == (-6, highest)
