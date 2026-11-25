"""Verbinding met één Omi-hanger via de Bluetooth-laag van Home Assistant.

Verbindt, telt de audiostroom (pakketten/s, verlies), leest batterij en knop, en houdt
bij via welke ontvanger (adapter of ESPHome-proxy) de verbinding loopt. De Opus-frames
gaan naar de audioluisteraars (het gesprek, zie gesprek.py).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import logging
import struct
import time
from typing import Any
import warnings

from bleak import BleakClient
from bleak.backends.device import BLEDevice
import bleak_retry_connector

from homeassistant.components import bluetooth
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback

from .const import (
    AUDIO_CHAR,
    BATTERIJ_CHAR,
    BATTERIJ_ELKE_S,
    CODEC_CHAR,
    HAPTIEK_CHAR,
    KNOP_CHAR,
    KNOP_GEBEURTENIS,
    MEETVENSTER_S,
    WACHT_MAX_S,
    WACHT_MIN_S,
)

_LOGGER = logging.getLogger(__name__)


class OmiHanger:
    """Houdt de verbinding met de hanger in stand en verzamelt meetwaarden."""

    def __init__(self, hass: HomeAssistant, address: str, naam: str) -> None:
        self.hass = hass
        self.address = address
        self.naam = naam

        self.verbonden = False
        self.ontvanger: str | None = None
        self.ontvanger_bron: str | None = None
        self.rssi: int | None = None
        self.codec: int | None = None
        self.mtu: int | None = None
        self.lege_sessies = 0
        self.batterij: int | None = None
        self.pakketten_per_s: float | None = None
        self.verlies_pct: float | None = None
        self.pakketten_totaal = 0
        self.verloren_totaal = 0
        self.verbindingen = 0
        self.stilvallen = 0
        self.verbonden_sinds: float | None = None
        self.laatste_fout: str | None = None
        self.gesprek: Any = None        # Gesprek, gezet door __init__

        self._listeners: list[CALLBACK_TYPE] = []
        self._knop_listeners: list[Callable[[str], None]] = []
        self._audio_listeners: list[Callable[[bytes], None]] = []
        self._task: asyncio.Task[None] | None = None
        self._client: BleakClient | None = None
        self._los = asyncio.Event()
        self._gezien = asyncio.Event()
        self._stop_adv: CALLBACK_TYPE | None = None
        self._venster_pakketten = 0
        self._venster_verloren = 0
        self._venster_bytes = 0
        self._venster_fragmenten = 0
        self._venster_lengtes: list[int] = []
        self._vorige_id: int | None = None
        self.notify_lengte: str | None = None
        self.bytes_per_s: float | None = None
        self.fragmenten_pct: float | None = None

    # ---- luisteraars -------------------------------------------------------

    @callback
    def async_add_listener(self, cb: CALLBACK_TYPE) -> CALLBACK_TYPE:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    @callback
    def async_add_knop_listener(self, cb: Callable[[str], None]) -> CALLBACK_TYPE:
        self._knop_listeners.append(cb)
        return lambda: self._knop_listeners.remove(cb)

    @callback
    def async_add_audio_listener(self, cb: Callable[[bytes], None]) -> CALLBACK_TYPE:
        """cb krijgt elk heel Opus-frame, zonder de kop van 3 bytes."""
        self._audio_listeners.append(cb)
        return lambda: self._audio_listeners.remove(cb)

    @callback
    def meld(self) -> None:
        self._meld()

    @callback
    def _meld(self) -> None:
        for cb in list(self._listeners):
            cb()

    # ---- starten en stoppen ------------------------------------------------

    @property
    def actief(self) -> bool:
        return self._task is not None

    @callback
    def async_start(self) -> None:
        """Begin op de achtergrond te verbinden; blokkeert de start van HA niet."""
        if self._task is not None:
            return
        self._stop_adv = bluetooth.async_register_callback(
            self.hass,
            self._advertentie,
            bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
        self._task = self.hass.async_create_background_task(
            self._lus(), f"omi {self.address}"
        )
        self._meld()

    async def async_stop(self) -> None:
        task, self._task = self._task, None
        if self._stop_adv:
            self._stop_adv()
            self._stop_adv = None
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._verbreek()
        self._meld()

    @callback
    def _advertentie(
        self, info: bluetooth.BluetoothServiceInfoBleak, _change: bluetooth.BluetoothChange
    ) -> None:
        self.rssi = info.rssi
        self._gezien.set()

    async def _verbreek(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            with contextlib.suppress(Exception):
                await client.disconnect()

    # ---- verbindingslus ----------------------------------------------------

    async def _lus(self) -> None:
        wacht = WACHT_MIN_S
        while True:
            try:
                if await self._sessie():
                    wacht = WACHT_MIN_S
                else:
                    wacht = min(wacht * 2, WACHT_MAX_S)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - de lus mag nooit stoppen
                self.laatste_fout = f"{type(err).__name__}: {err}"
                _LOGGER.warning("%s: %s", self.naam, self.laatste_fout)
                wacht = min(wacht * 2, WACHT_MAX_S)
            finally:
                await self._verbreek()
                if self.verbonden:
                    _LOGGER.info("%s: verbinding verbroken", self.naam)
                self.verbonden = False
                self.verbonden_sinds = None
                self.pakketten_per_s = None
                self.verlies_pct = None
                self._meld()
            await asyncio.sleep(wacht)

    def _ble_device(self) -> BLEDevice | None:
        return bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )

    async def _sessie(self) -> bool:
        """Eén verbinding van begin tot eind; loopt tot de verbinding wegvalt.

        True als er audio binnenkwam. Een verbinding die wegvalt zonder één audiopakket
        telt als mislukt, zodat de wachttijd oploopt.
        """
        ble = self._ble_device()
        if ble is None:
            # Niet in bereik (of nog verbonden met iets anders): wachten op een advertentie.
            self._gezien.clear()
            await self._gezien.wait()
            return True

        self._los.clear()
        client = await bleak_retry_connector.establish_connection(
            bleak_retry_connector.BleakClientWithServiceCache,
            ble,
            self.naam,
            disconnected_callback=lambda _c: self._los.set(),
            ble_device_callback=lambda: self._ble_device() or ble,
            # Geen servicecache: een ESPHome-proxy slaat bij een verbinding mét cache de
            # MTU-uitwisseling over. Dan blijft de MTU 23 en past een Opus-notificatie
            # (±80 bytes) er niet in: de hanger stuurt geen audio (gemeten 25-11-2026,
            # elke herverbinding via de proxy "mtu=23" en 0 pakketten). Kost ±2 s
            # servicediscovery per verbinding.
            use_services_cache=False,
        )
        self._client = client

        # De wrapper van HA onthoudt via welke scanner de verbinding loopt.
        scanner = getattr(client, "_connected_scanner", None)
        self.ontvanger = getattr(scanner, "name", None)
        self.ontvanger_bron = getattr(scanner, "source", None)
        self.mtu = await self._echte_mtu(client)

        try:
            self.codec = (await client.read_gatt_char(CODEC_CHAR))[0]
        except Exception:  # noqa: BLE001
            self.codec = None
        await self._lees_batterij()

        self._vorige_id = None
        self._venster_pakketten = self._venster_verloren = 0
        self._venster_bytes = self._venster_fragmenten = 0
        self._venster_lengtes = []
        await client.start_notify(AUDIO_CHAR, self._audio)
        await client.start_notify(KNOP_CHAR, self._knop)

        self.verbonden = True
        self.verbonden_sinds = time.time()
        self.verbindingen += 1
        self.laatste_fout = None
        _LOGGER.info(
            "%s: verbonden via %s (codec %s, mtu %s)",
            self.naam, self.ontvanger, self.codec, self.mtu,
        )
        self._meld()

        batterij_tijd = time.monotonic()
        begin_totaal = self.pakketten_totaal
        stroomt = False
        while not self._los.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._los.wait(), MEETVENSTER_S)
            if self._los.is_set():
                break

            n, verloren = self._venster_pakketten, self._venster_verloren
            lengtes, frag = self._venster_lengtes, self._venster_fragmenten
            self.bytes_per_s = round(self._venster_bytes / MEETVENSTER_S)
            self._venster_pakketten = self._venster_verloren = 0
            self._venster_bytes = self._venster_fragmenten = 0
            self._venster_lengtes = []
            self.pakketten_per_s = round(n / MEETVENSTER_S, 1)
            self.verlies_pct = round(100 * verloren / (n + verloren), 1) if n + verloren else None
            if n:
                # Heel frame of stukken? Een Opus-frame is ±80 bytes; past het niet in
                # één notificatie (kleine MTU), dan knipt de hanger het op en loopt het
                # derde kopbyte op (fragmenten).
                self.notify_lengte = f"{min(lengtes)}-{max(lengtes)}"
                self.fragmenten_pct = round(100 * frag / n, 1)
                _LOGGER.debug(
                    "%s: %s notificaties/s, %s bytes/s, lengte %s, fragmenten %s%%, verlies %s%%",
                    self.naam, self.pakketten_per_s, self.bytes_per_s,
                    self.notify_lengte, self.fragmenten_pct, self.verlies_pct,
                )
            if time.monotonic() - batterij_tijd > BATTERIJ_ELKE_S:
                batterij_tijd = time.monotonic()
                await self._lees_batterij()
            self._meld()

            # De hanger stuurt alleen audio als hij geluid hoort (VAD in de firmware):
            # in stilte komt er soms minutenlang niets, ook al staat de verbinding
            # (gemeten 25-11-2026 op de desktop: 0,5 tot 15 s voor het eerste pakket,
            # gaten tot 85 s). Stilte is dus geen storing en geen reden om opnieuw te
            # verbinden; we tellen alleen hoe vaak de stroom ophoudt.
            if n == 0 and stroomt:
                self.stilvallen += 1
                _LOGGER.debug("%s: audio gestopt (stilte)", self.naam)
            stroomt = n > 0
        if self.pakketten_totaal > begin_totaal:
            self.lege_sessies = 0
            return True
        self.lege_sessies += 1
        _LOGGER.warning(
            "%s: verbonden via %s (mtu %s) maar geen audio ontvangen (%s keer op rij)",
            self.naam, self.ontvanger, self.mtu, self.lege_sessies,
        )
        return False

    @staticmethod
    async def _echte_mtu(client: BleakClient) -> int | None:
        """De onderhandelde MTU.

        Op een lokale BlueZ-adapter geeft bleak standaard 23 terug zolang niemand de
        MTU heeft opgevraagd (gemeten 25-11-2026: hci0 "mtu 23"). Dat getal zegt dus
        niets; vraag hem bij BlueZ op. Via een ESPHome-proxy is hij al bekend.
        """
        backend = getattr(client, "_backend", None)
        if backend is not None and hasattr(backend, "_acquire_mtu") and getattr(
            backend, "_mtu_size", 0
        ) is None:
            try:
                await backend._acquire_mtu()  # noqa: SLF001
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("MTU niet op te vragen: %s", err)
                return None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return getattr(client, "mtu_size", None)

    async def _lees_batterij(self) -> None:
        if self._client is None:
            return
        try:
            self.batterij = (await self._client.read_gatt_char(BATTERIJ_CHAR))[0]
        except Exception:  # noqa: BLE001
            _LOGGER.debug("%s: batterij niet leesbaar", self.naam)

    # ---- notificaties ------------------------------------------------------

    def _audio(self, _char: Any, data: bytearray) -> None:
        # Kop: pakketnummer uint16 LE + volgnummer binnen het pakket.
        if len(data) < 3:
            return
        pid = data[0] | (data[1] << 8)
        if self._vorige_id is not None and pid != self._vorige_id:
            gat = (pid - self._vorige_id) & 0xFFFF
            if 1 < gat < 1000:
                self._venster_verloren += gat - 1
                self.verloren_totaal += gat - 1
        self._vorige_id = pid
        self._venster_bytes += len(data)
        self._venster_lengtes.append(len(data))
        self._venster_pakketten += 1
        self.pakketten_totaal += 1
        if data[2]:
            # Stuk van een opgeknipt frame (alleen bij een kleine MTU; sinds 0.1.3 niet
            # meer gezien). Niet bruikbaar voor de decoder: overslaan.
            self._venster_fragmenten += 1
            return
        frame = bytes(data[3:])
        for cb in list(self._audio_listeners):
            cb(frame)

    def _knop(self, _char: Any, data: bytearray) -> None:
        if len(data) < 4:
            return
        toestand = struct.unpack("<I", bytes(data[:4]))[0]
        if (soort := KNOP_GEBEURTENIS.get(toestand)) is None:
            return
        _LOGGER.debug("%s: knop %s", self.naam, soort)
        for cb in list(self._knop_listeners):
            cb(soort)

    async def tril(self, sterkte: int, keer: int = 1) -> None:
        """Sterkte 1/2/3 = 100/300/500 ms; keer = hoe vaak, met een korte pauze ertussen."""
        for i in range(keer):
            if self._client is None:
                return
            if i:
                await asyncio.sleep(0.1 + 0.2 * sterkte)
            try:
                await self._client.write_gatt_char(HAPTIEK_CHAR, bytes([sterkte]), response=True)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("%s: trillen mislukt: %s", self.naam, err)
                return

    def diagnose(self) -> dict[str, Any]:
        return {
            "actief": self.actief,
            "verbonden": self.verbonden,
            "ontvanger": self.ontvanger,
            "ontvanger_bron": self.ontvanger_bron,
            "rssi": self.rssi,
            "codec": self.codec,
            "mtu": self.mtu,
            "lege_sessies": self.lege_sessies,
            "batterij": self.batterij,
            "pakketten_per_s": self.pakketten_per_s,
            "verlies_pct": self.verlies_pct,
            "bytes_per_s": self.bytes_per_s,
            "notify_lengte": self.notify_lengte,
            "fragmenten_pct": self.fragmenten_pct,
            "pakketten_totaal": self.pakketten_totaal,
            "verloren_totaal": self.verloren_totaal,
            "verbindingen": self.verbindingen,
            "stilvallen": self.stilvallen,
            "laatste_fout": self.laatste_fout,
        }
