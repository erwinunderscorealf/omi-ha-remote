"""Config flow: de hanger wordt via Bluetooth ontdekt of uit een lijst gekozen."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from .const import DOMAIN


def _is_omi(info: BluetoothServiceInfoBleak) -> bool:
    return (info.name or "").startswith("Omi")


class OmiConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._ontdekt: BluetoothServiceInfoBleak | None = None
        self._gevonden: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._ontdekt = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._ontdekt is not None
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME], data={CONF_ADDRESS: self._ontdekt.address}
            )
        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_NAME, default=self._ontdekt.name or "Omi"): str}
            ),
            description_placeholders={"name": self._ontdekt.name},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            adres = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(adres, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME], data={CONF_ADDRESS: adres}
            )

        bekend = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if _is_omi(info) and info.address not in bekend:
                self._gevonden[info.address] = f"{info.name} ({info.address})"
        if not self._gevonden:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(self._gevonden),
                    vol.Required(CONF_NAME, default="Omi"): str,
                }
            ),
        )
