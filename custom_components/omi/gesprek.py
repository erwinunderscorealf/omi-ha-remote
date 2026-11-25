"""Spraak: tik op de hanger → opnemen → Assist-pipeline → antwoord op de speaker.

1. Tik → korte tril → opnemen (de laatste 0,4 s vóór de tik gaan mee).
2. Stilte (1,2 s) of een tweede tik → dubbele tril → de audio gaat door de pipeline.
3. Het antwoord (TTS) klinkt op de speaker die bij de huidige ontvanger hoort.
4. Wedervraag → na het antwoord korte tril en zonder tik nog eens luisteren.
5. Dubbeltik = nieuw gesprek. Fout = lange tril.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.components import stt
from homeassistant.components.assist_pipeline import (
    AudioSettings,
    PipelineEvent,
    PipelineEventType,
    async_pipeline_from_audio_stream,
)
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import (
    CONF_ONTVANGERS,
    CONF_PIPELINE,
    CONF_RUIMTE,
    CONF_SPEAKER,
    EVENT_GESPREK,
    EVENT_LUISTEREN_KLAAR,
    EVENT_LUISTERT,
    MIN_SPRAAK_S,
    NA_ANTWOORD_PER_TEKEN_S,
    NA_ANTWOORD_S,
    OPUS_CODECS,
    PIPELINE_TIMEOUT_S,
    PIPELINE_VOORKEUR,
    TRIL_NEGEER_S,
    VERVOLG_WACHT_S,
    VOORLOOP_PAKKETTEN,
)
from .spraak import Opname, OpusDecoder

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .hanger import OmiHanger

_LOGGER = logging.getLogger(__name__)

# Een kaal "Oké." is vrijwel altijd een valse activatie: niet hardop herhalen.
_STIL = {"oké", "oke", "ok", "okay"}


class Gesprek:
    """Eén gesprek tegelijk per hanger."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hanger: OmiHanger) -> None:
        self.hass = hass
        self.entry = entry
        self.hanger = hanger
        self.status = "idle"            # idle / listening / processing / responding
        self.laatst_gehoord: str | None = None
        self.laatste_antwoord: str | None = None
        self.laatste_fout: str | None = None
        self._voorloop: deque[tuple[float, bytes]] = deque(maxlen=VOORLOOP_PAKKETTEN)
        self._opname: Opname | None = None
        self._decoder: OpusDecoder | None = None
        self._stop = asyncio.Event()
        self._bezig = False
        self._gesprek_id: str | None = None

    # ---- invoer van de hanger ----------------------------------------------

    def audio(self, frame: bytes) -> None:
        """Eén Opus-frame (zonder de kop van 3 bytes)."""
        if self._opname is None or self._decoder is None:
            self._voorloop.append((time.monotonic(), frame))
            return
        self._opname.voeg_toe(self._decoder.decode(frame))
        if (reden := self._opname.klaar()) and not self._stop.is_set():
            _LOGGER.debug("%s: einde opname (%s)", self.hanger.naam, reden)
            self._stop.set()

    def knop(self, soort: str) -> None:
        if soort == "single_tap":
            self.hass.async_create_background_task(self.tik(), "omi tik")
        elif soort == "double_tap":
            self.hass.async_create_background_task(self.nieuw_gesprek(), "omi nieuw gesprek")

    # ---- gesprek -----------------------------------------------------------

    async def nieuw_gesprek(self) -> None:
        self._gesprek_id = None
        _LOGGER.debug("%s: nieuw gesprek", self.hanger.naam)
        await self.hanger.tril(2)

    async def tik(self, vervolg: bool = False) -> None:
        if self._opname is not None:          # tweede tik: klaar met praten
            self._stop.set()
            return
        if self._bezig:
            _LOGGER.debug("%s: nog bezig met de vorige vraag", self.hanger.naam)
            return
        if self.hanger.codec not in OPUS_CODECS:
            _LOGGER.warning("%s: codec %s wordt niet ondersteund", self.hanger.naam, self.hanger.codec)
            await self.hanger.tril(3)
            return

        self._bezig = True
        nog_eens = False
        ruimte, speaker = self._kamer()
        try:
            nog_eens = await self._vraag_en_antwoord(vervolg, ruimte, speaker)
        except Exception:
            _LOGGER.exception("%s: vraag mislukt", self.hanger.naam)
            await self.hanger.tril(3)
        finally:
            self._opname = None
            self._decoder = None
            self._bezig = False
            self._zet_status("idle")
        # Net als de spraakkastjes: na een wedervraag één keer zonder tik doorluisteren.
        if nog_eens and not vervolg:
            await self.tik(vervolg=True)

    async def _vraag_en_antwoord(self, vervolg: bool, ruimte: str, speaker: str | None) -> bool:
        """Geeft True als er een wedervraag is uitgesproken."""
        self._decoder = OpusDecoder()
        self._stop.clear()
        if vervolg:
            # Geen voorloop (staart van het antwoord); de tril hieronder klinkt in de
            # microfoon even hard als spraak, dus het begin niet meetellen.
            opname = Opname(wacht_s=VERVOLG_WACHT_S)
            opname.negeer_s = TRIL_NEGEER_S
        else:
            # Alleen wat vlak vóór de tik binnenkwam: in stilte stuurt de hanger niets,
            # dus de laatste frames in de buffer kunnen minuten oud zijn.
            grens = time.monotonic() - VOORLOOP_PAKKETTEN * 0.02 - 0.2
            voorloop = b"".join(
                self._decoder.decode(f) for t, f in self._voorloop if t >= grens
            )
            opname = Opname(voorloop)
        self._voorloop.clear()
        self._opname = opname
        self._zet_status("listening")
        self.hass.bus.async_fire(EVENT_LUISTERT, {"room": ruimte, "device_id": self._device_id()})
        await self.hanger.tril(1)

        # De hanger stuurt in stilte niets; daarom niet alleen bij binnenkomende audio
        # kijken of de vraag af is, maar ook op de klok.
        while not self._stop.is_set() and not opname.klaar():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), 0.2)
        self._opname = None
        pcm = bytes(opname.pcm)
        await self.hanger.tril(1, keer=2)
        _LOGGER.debug(
            "%s: opname %.1f s, spraak %.1f s, ruimte %s",
            self.hanger.naam, opname.duur_s, opname.spraak_s, ruimte,
        )
        if opname.spraak_s < MIN_SPRAAK_S:
            self.hass.bus.async_fire(EVENT_LUISTEREN_KLAAR, {"room": ruimte})
            return False

        self._zet_status("processing")
        uit = await self._pipeline(pcm, ruimte)
        self.laatst_gehoord, self.laatste_antwoord, self.laatste_fout = (
            uit["tekst"], uit["antwoord"], uit["fout"],
        )
        self.hass.bus.async_fire(
            EVENT_GESPREK,
            {
                "room": ruimte,
                "wake_word": "omi",
                "heard": uit["tekst"] or "",
                "answer": uit["antwoord"] or "",
                "error": uit["fout"] or "",
                "device_id": self._device_id(),
            },
        )
        _LOGGER.debug(
            "%s: gehoord %r, antwoord %r, fout %r",
            self.hanger.naam, uit["tekst"], uit["antwoord"], uit["fout"],
        )
        if uit["fout"]:
            await self.hanger.tril(3)
            return False

        antwoord = (uit["antwoord"] or "").strip()
        if not antwoord or not uit["url"]:
            return False
        if antwoord.rstrip(".! ").lower() in _STIL:
            return False
        if speaker is None:
            _LOGGER.warning(
                "%s: geen speaker ingesteld voor ontvanger %s; zie de opties",
                self.hanger.naam, self.hanger.ontvanger,
            )
            return False

        self._zet_status("responding")
        t0 = time.monotonic()
        await self._speel(speaker, uit["url"])
        if not uit["vervolg"]:
            return False
        # Pas doorluisteren als het antwoord is uitgesproken (play_media wacht daar niet
        # bij elke speler op); anders hoort de hanger de wedervraag zelf terug.
        nog = NA_ANTWOORD_S + NA_ANTWOORD_PER_TEKEN_S * len(antwoord) - (time.monotonic() - t0)
        if nog > 0:
            await asyncio.sleep(nog)
        return True

    # ---- pipeline en afspelen ----------------------------------------------

    async def _pipeline(self, pcm: bytes, ruimte: str) -> dict[str, Any]:
        uit: dict[str, Any] = {
            "tekst": None, "antwoord": None, "url": None, "fout": None, "vervolg": False,
        }

        def gebeurtenis(ev: PipelineEvent) -> None:
            d = ev.data or {}
            if ev.type == PipelineEventType.STT_END:
                uit["tekst"] = (d.get("stt_output") or {}).get("text")
                self.hass.bus.async_fire(EVENT_LUISTEREN_KLAAR, {"room": ruimte})
            elif ev.type == PipelineEventType.INTENT_END:
                io = d.get("intent_output") or {}
                self._gesprek_id = io.get("conversation_id") or self._gesprek_id
                uit["antwoord"] = (
                    ((io.get("response") or {}).get("speech") or {}).get("plain") or {}
                ).get("speech")
                uit["vervolg"] = bool(io.get("continue_conversation")) or (
                    (uit["antwoord"] or "").rstrip().endswith("?")
                )
            elif ev.type == PipelineEventType.TTS_END:
                uit["url"] = (d.get("tts_output") or {}).get("url")
            elif ev.type == PipelineEventType.ERROR:
                uit["fout"] = f"{d.get('code')} {d.get('message')}"

        async def stroom() -> AsyncIterator[bytes]:
            for i in range(0, len(pcm), 3200):        # blokken van 100 ms
                yield pcm[i : i + 3200]

        pipeline = self.entry.options.get(CONF_PIPELINE)
        try:
            async with asyncio.timeout(PIPELINE_TIMEOUT_S):
                await async_pipeline_from_audio_stream(
                    self.hass,
                    context=Context(),
                    event_callback=gebeurtenis,
                    stt_metadata=stt.SpeechMetadata(
                        language="",            # de pipeline vult zijn eigen taal in
                        format=stt.AudioFormats.WAV,
                        codec=stt.AudioCodecs.PCM,
                        bit_rate=stt.AudioBitRates.BITRATE_16,
                        sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
                        channel=stt.AudioChannels.CHANNEL_MONO,
                    ),
                    stt_stream=stroom(),
                    pipeline_id=None if pipeline in (None, PIPELINE_VOORKEUR) else pipeline,
                    conversation_id=self._gesprek_id,
                    device_id=self._device_id(),
                    # Wij bepalen het einde van de vraag al; de pipeline hoeft niet te knippen.
                    audio_settings=AudioSettings(is_vad_enabled=False),
                )
        except TimeoutError:
            uit["fout"] = uit["fout"] or "timeout"
        except Exception as err:  # noqa: BLE001 - bijvoorbeeld PipelineNotFound
            uit["fout"] = uit["fout"] or f"{type(err).__name__}: {err}"
        finally:
            # Ook bij een fout vóór het einde van de spraakherkenning de muziek terugzetten.
            if uit["tekst"] is None:
                self.hass.bus.async_fire(EVENT_LUISTEREN_KLAAR, {"room": ruimte})
        return uit

    async def _speel(self, speaker: str, url: str) -> None:
        if url.startswith("/"):
            with contextlib.suppress(NoURLAvailableError):
                url = get_url(self.hass, prefer_external=False) + url
        try:
            async with asyncio.timeout(60):
                await self.hass.services.async_call(
                    "media_player",
                    "play_media",
                    {
                        "entity_id": speaker,
                        "media_content_id": url,
                        "media_content_type": "music",
                        "announce": True,
                    },
                    blocking=True,
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("%s: afspelen op %s mislukt: %s", self.hanger.naam, speaker, err)

    # ---- hulpjes -----------------------------------------------------------

    def _kamer(self) -> tuple[str, str | None]:
        """(ruimte, speaker) bij de ontvanger die de verbinding nu draagt."""
        regel = (self.entry.options.get(CONF_ONTVANGERS) or {}).get(self.hanger.ontvanger_bron or "", {})
        ruimte = regel.get(CONF_RUIMTE) or self.hanger.ontvanger or ""
        return ruimte, regel.get(CONF_SPEAKER)

    def _device_id(self) -> str | None:
        apparaat = dr.async_get(self.hass).async_get_device(
            connections={(CONNECTION_BLUETOOTH, self.hanger.address)}
        )
        return apparaat.id if apparaat else None

    def _zet_status(self, status: str) -> None:
        self.status = status
        self.hanger.meld()

    def diagnose(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "pipeline": self.entry.options.get(CONF_PIPELINE),
            "ontvangers": self.entry.options.get(CONF_ONTVANGERS),
            "laatste_fout": self.laatste_fout,
        }
