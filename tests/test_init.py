"""Entry setup/unload, services, and the push-update path, with the UDP client mocked."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.c4_audio.const import CONF_MODEL, DOMAIN, MODEL_AMP108
from custom_components.c4_audio.protocol import ParsedPacket

SERVICES = ("send_command", "set_route", "turn_off_all", "turn_on_all")


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
