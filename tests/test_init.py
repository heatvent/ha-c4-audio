"""Entry setup/unload, services, and the push-update path, with the UDP client mocked."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.c4_audio.const import (
    CONF_MODEL,
    DOMAIN,
    MODEL_8AMP1,
    MODEL_AMP16,
    MODEL_AMP108,
)
from custom_components.c4_audio.protocol import ParsedPacket
from custom_components.c4_audio.udp_client import ProbeIdentity, async_probe_identity

SERVICES = ("send_command", "set_route", "turn_off_all", "turn_on_all")


@pytest.fixture(autouse=True)
def _storage(hass_storage):
    """Keep the last-source store in memory."""


def _reply(*args: str) -> ParsedPacket:
    # n01 makes every list poll a no-op, so only the firmware reply matters.
    return ParsedPacket("reply", 1, "n01", None, list(args), "reply")


@pytest.fixture
def mock_udp():
    with (
        patch("custom_components.c4_audio.udp_client.C4UdpClient.async_start", AsyncMock()),
        patch("custom_components.c4_audio.udp_client.C4UdpClient.async_stop", AsyncMock()) as stop,
        patch(
            "custom_components.c4_audio.udp_client.C4UdpClient.async_send",
            AsyncMock(return_value=_reply('"1.2.3"')),
        ),
    ):
        yield stop


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Amp",
        data={CONF_HOST: "192.0.2.10", CONF_PORT: 8750, CONF_MODEL: MODEL_AMP108},
    )
    entry.add_to_hass(hass)
    return entry


async def test_services_registered_without_entries(hass: HomeAssistant, enable_custom_integrations) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    for service in SERVICES:
        assert hass.services.has_service(DOMAIN, service)


async def test_setup_and_unload(hass: HomeAssistant, enable_custom_integrations, entry, mock_udp) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.state.firmware == "1.2.3"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    mock_udp.assert_awaited()
    # Services stay registered for automations even with no entry loaded.
    assert hass.services.has_service(DOMAIN, "send_command")


async def test_failed_platform_unload_keeps_socket(hass: HomeAssistant, enable_custom_integrations, entry, mock_udp) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    mock_udp.reset_mock()
    with patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)):
        from custom_components.c4_audio import async_unload_entry

        assert await async_unload_entry(hass, entry) is False
    mock_udp.assert_not_awaited()


async def test_status_frame_does_not_reschedule_poll(hass: HomeAssistant, enable_custom_integrations, entry, mock_udp) -> None:
    """A chatty chassis must not keep pushing the next full poll back."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    scheduled = coordinator._unsub_refresh
    assert scheduled is not None

    status = ParsedPacket("status", None, None, "c4.amp.mute", ["01", "01"], "status")
    coordinator._on_packet(status)
    coordinator._on_udp_activity()
    await hass.async_block_till_done()

    assert coordinator.state.zones[1].muted is True
    assert coordinator._unsub_refresh is scheduled


async def test_migration_strips_switch_link_and_keeps_amp_ids(
    hass: HomeAssistant, enable_custom_integrations, mock_udp
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Amp",
        data={
            CONF_HOST: "192.0.2.10",
            CONF_PORT: 8750,
            CONF_MODEL: MODEL_AMP16,
            "ident": "amp-ident",
            "zones": {"1": {"name": "Kitchen", "area_id": None}},
            "switch_feeds": "1=1",
        },
        options={"on_volume": 12, "switch_entry_id": "abc", "switch_feeds": "1=2"},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    before = registry.async_get_or_create(
        "media_player",
        DOMAIN,
        "amp-ident_zone_1",
        config_entry=entry,
        suggested_object_id="my_renamed_kitchen",
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (entry.version, entry.minor_version) == (1, 2)
    assert "switch_feeds" not in entry.data
    assert entry.options == {"on_volume": 12}
    assert registry.async_get(before.entity_id).unique_id == "amp-ident_zone_1"
    assert {e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)} == {
        f"amp-ident_{suffix}"
        for suffix in (
            "zone_1",
            "zone_1_source",
            "zone_1_bass",
            "zone_1_treble",
            "all_zones",
            "all_on",
            "all_off",
            "udp_activity",
        )
    }


async def test_old_switch_entry_fails_with_a_clear_error(
    hass: HomeAssistant, enable_custom_integrations, mock_udp
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Switch",
        data={CONF_HOST: "192.0.2.11", CONF_PORT: 8750, CONF_MODEL: "c4_16zamsv3_b"},
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert "no longer supported" in entry.reason

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_an_amp"


@pytest.mark.parametrize(
    ("info", "ain_reply", "not_amp", "model"),
    [
        ("x", ParsedPacket("reply", 1, "000", "c4.amp.ain", ["00"] * 4, ""), False, MODEL_AMP108),
        (
            "v1_8chanamp:c4-8amp1-b:00:0f:ff:00:00:01",
            ParsedPacket("reply", 1, "000", "c4.amp.ain", ["00"] * 4, ""),
            False,
            MODEL_8AMP1,
        ),
        (
            "v3_16chanamp:c4-16amp3-b:00:0f:ff:00:00:01",
            ParsedPacket("reply", 1, "000", "c4.amp.ain", ["00"] * 8, ""),
            False,
            MODEL_AMP16,
        ),
        ("x", ParsedPacket("reply", 1, None, None, [], ""), True, None),  # audio switch: empty 0r
        ("x", None, False, None),  # lost packet is not proof of anything
    ],
)
async def test_probe_classifies_amps(hass: HomeAssistant, info, ain_reply, not_amp, model) -> None:
    async def send(_self, _prefix, body, **_kwargs):
        return ain_reply if body == "c4.amp.ain" else _reply(f'"{info}"')

    with (
        patch("custom_components.c4_audio.udp_client.C4UdpClient.async_start", AsyncMock()),
        patch("custom_components.c4_audio.udp_client.C4UdpClient.async_send", send),
    ):
        identity = await async_probe_identity("192.0.2.12", 8750, 1.0)
    assert identity.not_amp is not_amp
    assert identity.model_id == model


async def _start_manual(hass: HomeAssistant):
    with patch("custom_components.c4_audio.config_flow.async_sddp_search", AsyncMock(return_value=[])):
        return await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})


def _probe(identity: ProbeIdentity):
    return patch(
        "custom_components.c4_audio.config_flow.async_probe_identity", AsyncMock(return_value=identity)
    )


MANUAL = {"name": "Amp", CONF_HOST: "192.0.2.12", CONF_PORT: 8750, CONF_MODEL: MODEL_AMP16}


async def test_manual_setup_rejects_the_audio_switch(hass: HomeAssistant, enable_custom_integrations) -> None:
    flow = await _start_manual(hass)
    with _probe(ProbeIdentity("1", "switch", None, not_amp=True)):
        result = await hass.config_entries.flow.async_configure(flow["flow_id"], dict(MANUAL))
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "not_an_amp"}


async def test_manual_setup_and_options(hass: HomeAssistant, enable_custom_integrations, mock_udp) -> None:
    flow = await _start_manual(hass)
    with _probe(ProbeIdentity("1", "Amp-Ident", MODEL_AMP16)):
        result = await hass.config_entries.flow.async_configure(flow["flow_id"], dict(MANUAL))
    assert result["step_id"] == "inputs"
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {"input_1_name": "WiiM Pro"})
    assert result["step_id"] == "outputs"
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {"zone_1_name": "Kitchen"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state is ConfigEntryState.LOADED
    assert (entry.version, entry.minor_version) == (1, 2)
    assert entry.runtime_data.media_source_list() == ["WiiM Pro"]

    for step, data in (
        ("inputs", {"input_1_name": "WiiM Pro", "input_2_name": "Tuner"}),
        ("outputs", {"zone_1_name": "Kitchen"}),
        ("settings", {"on_volume": 50, "max_volume": 40, "poll_interval": 15, "udp_timeout": 1.5}),
    ):
        menu = await hass.config_entries.options.async_init(entry.entry_id)
        form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": step})
        assert form["step_id"] == step
        done = await hass.config_entries.options.async_configure(form["flow_id"], data)
        assert done["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
    assert entry.options["on_volume"] == 40
    assert entry.runtime_data.media_source_list() == ["WiiM Pro", "Tuner"]


async def test_select_source_on_off_zone_sends_amp_commands_in_order(
    hass: HomeAssistant, enable_custom_integrations, entry, mock_udp
) -> None:
    hass.config_entries.async_update_entry(entry, data={**entry.data, "source_names": "WiiM Pro\nTuner"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    coordinator.client.async_send.reset_mock()
    coordinator.client.async_send.return_value = ParsedPacket("reply", 1, "000", None, [], "")
    await coordinator.async_select_source(2, "Tuner")
    await hass.async_block_till_done()
    sent = [call.args for call in coordinator.client.async_send.await_args_list][:5]
    assert sent == [
        ("0s", "c4.amp.psave 00"),
        ("0g", "c4.amp.digi 02"),
        ("0s", "c4.amp.out 02 02"),
        ("0s", "c4.amp.chvol 02 a5"),
        ("0s", "c4.amp.mute 02 00"),
    ]
