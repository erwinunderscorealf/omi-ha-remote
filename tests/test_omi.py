"""Rooktests: laden, entiteiten, switch, verliesmeting en knop."""

import asyncio
from unittest.mock import patch

from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.omi.const import DOMAIN
from custom_components.omi.hanger import OmiHanger

ADRES = "AA:BB:CC:DD:EE:FF"


async def _opzet(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Omi Test", data={CONF_ADDRESS: ADRES}, unique_id=ADRES)
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, "homeassistant", {})
    with patch("custom_components.omi.hanger.bluetooth.async_register_callback", return_value=lambda: None):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_entiteiten_en_switch(hass: HomeAssistant, enable_bluetooth) -> None:
    gestart = asyncio.Event()

    async def nep_lus(self):
        gestart.set()
        await asyncio.Event().wait()

    with patch.object(OmiHanger, "_lus", nep_lus):
        entry = await _opzet(hass)
        await asyncio.wait_for(gestart.wait(), 2)

        ids = sorted(e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id))
        print(ids)
        assert "binary_sensor.omi_test_connected" in ids
        assert "sensor.omi_test_battery" in ids
        assert "switch.omi_test_connect" in ids
        assert "event.omi_test_button" in ids
        assert hass.states.get("sensor.omi_test_assistant").state == "idle"
        assert hass.states.get("binary_sensor.omi_test_connected").state == "off"
        assert hass.states.get("switch.omi_test_connect").state == "on"

        await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.omi_test_connect"}, blocking=True)
        assert hass.states.get("switch.omi_test_connect").state == "off"
        assert not entry.runtime_data.actief

        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_verlies_en_knop(hass: HomeAssistant) -> None:
    h = OmiHanger(hass, ADRES, "Omi")
    gedrukt = []
    h.async_add_knop_listener(gedrukt.append)
    for pid in (1, 2, 3, 6, 7):          # 4 en 5 ontbreken
        h._audio(None, bytearray([pid, 0, 0, 0xAA]))
    h._audio(None, bytearray([0xFF, 0xFF, 0]))   # 65535 → gat van ~65k: geen verlies tellen
    h._audio(None, bytearray([0, 0, 0]))         # wrap naar 0: aansluitend
    assert h._venster_pakketten == 7
    assert h.verloren_totaal == 2
    h._knop(None, bytearray([2, 0, 0, 0]))
    h._knop(None, bytearray([5, 0, 0, 0]))
    assert gedrukt == ["double_tap"]


def test_audio_naar_luisteraar(hass: HomeAssistant) -> None:
    h = OmiHanger(hass, ADRES, "Omi")
    frames = []
    h.async_add_audio_listener(frames.append)
    h._audio(None, bytearray([1, 0, 0, 0xAA, 0xBB]))
    h._audio(None, bytearray([2, 0, 1, 0xCC]))      # fragment: niet doorgeven
    assert frames == [bytes([0xAA, 0xBB])]
