"""Meetsensoren van de hanger."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OmiConfigEntry
from .entity import OmiEntiteit
from .hanger import OmiHanger


@dataclass(frozen=True, kw_only=True)
class OmiSensorBeschrijving(SensorEntityDescription):
    waarde: Callable[[OmiHanger], Any]
    attributen: Callable[[OmiHanger], dict[str, Any]] | None = None


DIAG = EntityCategory.DIAGNOSTIC

SENSOREN = (
    OmiSensorBeschrijving(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        waarde=lambda h: h.batterij,
    ),
    OmiSensorBeschrijving(
        key="receiver",
        translation_key="receiver",
        waarde=lambda h: h.ontvanger if h.verbonden else None,
        attributen=lambda h: {"source": h.ontvanger_bron if h.verbonden else None},
    ),
    OmiSensorBeschrijving(
        key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=DIAG,
        entity_registry_enabled_default=False,
        waarde=lambda h: h.rssi,
    ),
    OmiSensorBeschrijving(
        key="audio_rate",
        translation_key="audio_rate",
        native_unit_of_measurement="packets/s",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=DIAG,
        waarde=lambda h: h.pakketten_per_s,
    ),
    OmiSensorBeschrijving(
        key="audio_loss",
        translation_key="audio_loss",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=DIAG,
        waarde=lambda h: h.verlies_pct,
        attributen=lambda h: {
            "packets_total": h.pakketten_totaal,
            "lost_total": h.verloren_totaal,
        },
    ),
    OmiSensorBeschrijving(
        key="connects",
        translation_key="connects",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=DIAG,
        waarde=lambda h: h.verbindingen,
    ),
    OmiSensorBeschrijving(
        key="stalls",
        translation_key="stalls",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=DIAG,
        waarde=lambda h: h.stilvallen,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: OmiConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(OmiSensor(entry.runtime_data, b) for b in SENSOREN)


class OmiSensor(OmiEntiteit, SensorEntity):
    entity_description: OmiSensorBeschrijving

    def __init__(self, hanger: OmiHanger, beschrijving: OmiSensorBeschrijving) -> None:
        super().__init__(hanger, beschrijving.key)
        self.entity_description = beschrijving
        self._attr_translation_key = beschrijving.translation_key

    @property
    def native_value(self) -> Any:
        return self.entity_description.waarde(self._hanger)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributen is None:
            return None
        return self.entity_description.attributen(self._hanger)
