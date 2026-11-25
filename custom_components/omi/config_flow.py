"""Config flow: de hanger wordt via Bluetooth ontdekt of uit een lijst gekozen."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.assist_pipeline import async_get_pipelines
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_current_scanners,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_ONTVANGER,
    CONF_ONTVANGERS,
    CONF_PIPELINE,
    CONF_RUIMTE,
    CONF_SPEAKER,
    DOMAIN,
    PIPELINE_VOORKEUR,
)


def _is_omi(info: BluetoothServiceInfoBleak) -> bool:
    return (info.name or "").startswith("Omi")


class OmiConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OmiOptionsFlow:
        return OmiOptionsFlow()

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


class OmiOptionsFlow(OptionsFlow):
    """Pipeline kiezen, en per ontvanger de speaker en ruimte.

    Het antwoord klinkt op de speaker van de ontvanger die de verbinding op dat moment
    draagt: loopt de hanger mee naar een andere kamer, dan volgt het antwoord.
    """

    def __init__(self) -> None:
        self._pipeline: str | None = None
        self._ontvangers: dict[str, dict[str, str]] | None = None
        self._bron: str | None = None

    def _scanners(self) -> dict[str, str]:
        return {
            s.source: s.name or s.source
            for s in async_current_scanners(self.hass)
            if s.connectable
        }

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._ontvangers is None:
            self._ontvangers = {
                k: dict(v) for k, v in (self.config_entry.options.get(CONF_ONTVANGERS) or {}).items()
            }
            self._pipeline = self.config_entry.options.get(CONF_PIPELINE, PIPELINE_VOORKEUR)

        if user_input is not None:
            self._pipeline = user_input[CONF_PIPELINE]
            if bron := user_input.get(CONF_ONTVANGER):
                self._bron = bron
                return await self.async_step_receiver()
            return self.async_create_entry(
                data={CONF_PIPELINE: self._pipeline, CONF_ONTVANGERS: self._ontvangers}
            )

        pipelines = [SelectOptionDict(value=PIPELINE_VOORKEUR, label=PIPELINE_VOORKEUR)]
        pipelines += [
            SelectOptionDict(value=p.id, label=p.name) for p in async_get_pipelines(self.hass)
        ]
        scanners = self._scanners()
        for bron in self._ontvangers:
            scanners.setdefault(bron, bron)   # ingesteld maar nu niet in de lucht
        ontvangers = []
        for bron, naam in scanners.items():
            regel = self._ontvangers.get(bron) or {}
            achter = " → ".join(x for x in (regel.get(CONF_RUIMTE), regel.get(CONF_SPEAKER)) if x)
            ontvangers.append(
                SelectOptionDict(value=bron, label=f"{naam}: {achter}" if achter else naam)
            )

        schema: dict[Any, Any] = {
            vol.Required(CONF_PIPELINE, default=self._pipeline): SelectSelector(
                SelectSelectorConfig(
                    options=pipelines,
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="pipeline",
                )
            ),
        }
        if ontvangers:
            schema[vol.Optional(CONF_ONTVANGER)] = SelectSelector(
                SelectSelectorConfig(options=ontvangers, mode=SelectSelectorMode.DROPDOWN)
            )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))

    async def async_step_receiver(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._ontvangers is not None and self._bron is not None
        if user_input is not None:
            regel = {
                k: v.strip() if isinstance(v, str) else v
                for k, v in user_input.items()
                if k in (CONF_SPEAKER, CONF_RUIMTE) and v
            }
            if regel:
                self._ontvangers[self._bron] = regel
            else:
                self._ontvangers.pop(self._bron, None)
            self._bron = None
            return await self.async_step_init()

        regel = self._ontvangers.get(self._bron) or {}
        schema: dict[Any, Any] = {
            vol.Optional(
                CONF_SPEAKER, description={"suggested_value": regel.get(CONF_SPEAKER)}
            ): EntitySelector(EntitySelectorConfig(domain="media_player")),
            vol.Optional(
                CONF_RUIMTE, description={"suggested_value": regel.get(CONF_RUIMTE)}
            ): TextSelector(),
        }
        return self.async_show_form(
            step_id="receiver",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "receiver": self._scanners().get(self._bron, self._bron)
            },
        )
