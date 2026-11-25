"""Omi-hanger als Home Assistant-integratie: praten met een Assist-pipeline."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .gesprek import Gesprek
from .hanger import OmiHanger

PLATFORMS = [Platform.BINARY_SENSOR, Platform.EVENT, Platform.SENSOR, Platform.SWITCH]

type OmiConfigEntry = ConfigEntry[OmiHanger]


async def async_setup_entry(hass: HomeAssistant, entry: OmiConfigEntry) -> bool:
    """Zet de entiteiten neer; de switch 'verbinden' start de verbinding op de achtergrond."""
    hanger = OmiHanger(hass, entry.data[CONF_ADDRESS], entry.title)
    gesprek = Gesprek(hass, entry, hanger)
    hanger.gesprek = gesprek
    entry.runtime_data = hanger
    entry.async_on_unload(hanger.async_add_audio_listener(gesprek.audio))
    entry.async_on_unload(hanger.async_add_knop_listener(gesprek.knop))
    entry.async_on_unload(hanger.async_stop)
    # Opties (pipeline, ontvanger → speaker) worden bij elk gebruik gelezen: geen herlaad nodig.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OmiConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
