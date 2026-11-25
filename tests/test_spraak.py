"""Spraakversie: decoder, einde-van-de-vraag, opties en een heel gesprek."""

import asyncio
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from homeassistant.components.assist_pipeline import PipelineEvent, PipelineEventType
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.omi import spraak
from custom_components.omi.const import DOMAIN
from custom_components.omi.gesprek import Gesprek
from custom_components.omi.hanger import OmiHanger
from custom_components.omi.spraak import Opname, OpusDecoder

ADRES = "AA:BB:CC:DD:EE:FF"
LUID = (np.sin(np.arange(320) / 3) * 1000).astype(np.int16).tobytes()   # 20 ms, rms ±700
STIL = bytes(640)


def _opus_frames(n: int) -> list[bytes]:
    import av

    enc = av.CodecContext.create("libopus", "w")
    enc.sample_rate = 16000
    enc.layout = "mono"
    enc.format = "s16"
    enc.open()
    uit = []
    for _ in range(n):
        f = av.AudioFrame.from_ndarray(np.frombuffer(LUID, np.int16)[None, :], format="s16", layout="mono")
        f.sample_rate = 16000
        uit += [bytes(p) for p in enc.encode(f)]
    return uit


def test_decoder() -> None:
    d = OpusDecoder()
    pcm = b"".join(d.decode(f) for f in _opus_frames(25))
    assert len(pcm) > 0.3 * 16000 * 2         # het grootste deel komt terug, 16 kHz s16
    d.decode(b"\x00\x01rommel")            # geen uitzondering


def test_opname_stilte_en_wegblijven(monkeypatch) -> None:
    nu = [100.0]
    monkeypatch.setattr(spraak.time, "monotonic", lambda: nu[0])
    o = Opname()
    for _ in range(25):                       # 0,5 s tikgeluid: genegeerd
        o.voeg_toe(LUID)
    assert o.spraak_s == 0
    for _ in range(25):
        o.voeg_toe(LUID)
    assert o.klaar() is None
    for _ in range(61):                       # 1,22 s stille audio
        o.voeg_toe(STIL)
    assert o.klaar() == "stilte"

    o = Opname()
    o.negeer_s = 0
    for _ in range(25):
        o.voeg_toe(LUID)
    assert o.klaar() is None
    nu[0] += 1.5                              # hanger stuurt niets meer (firmware-VAD)
    assert o.klaar() == "stilte"

    o = Opname(wacht_s=6)
    nu[0] += 6.1
    assert o.klaar() == "geen antwoord"


async def test_opties(hass: HomeAssistant, enable_bluetooth) -> None:
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(domain=DOMAIN, title="Omi", data={CONF_ADDRESS: ADRES}, unique_id=ADRES)
    entry.add_to_hass(hass)
    scanner = type("S", (), {"source": "11:22", "name": "proxy kamer", "connectable": True})()
    with (
        patch("custom_components.omi.config_flow.async_current_scanners", return_value=[scanner]),
        patch("custom_components.omi.config_flow.async_get_pipelines", return_value=[]),
    ):
        r = await hass.config_entries.options.async_init(entry.entry_id)
        assert r["type"] is FlowResultType.FORM and r["step_id"] == "init"
        r = await hass.config_entries.options.async_configure(
            r["flow_id"], {"pipeline": "preferred", "receiver": "11:22"}
        )
        assert r["step_id"] == "receiver"
        r = await hass.config_entries.options.async_configure(
            r["flow_id"], {"speaker": "media_player.kamer", "room": " Kamer "}
        )
        assert r["step_id"] == "init"
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"pipeline": "preferred"})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "pipeline": "preferred",
        "receivers": {"11:22": {"speaker": "media_player.kamer", "room": "Kamer"}},
    }


class NepDecoder:
    def decode(self, frame: bytes) -> bytes:
        return frame


@pytest.mark.parametrize("wedervraag", [False, True])
async def test_gesprek(hass: HomeAssistant, wedervraag: bool) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ADDRESS: ADRES},
        options={"pipeline": "abc", "receivers": {"11:22": {"speaker": "media_player.kamer", "room": "Kamer"}}},
    )
    h = OmiHanger(hass, ADRES, "Omi")
    h.codec, h.ontvanger_bron = 21, "11:22"
    h.tril = AsyncMock()
    g = Gesprek(hass, entry, h)
    afspelen = async_mock_service(hass, "media_player", "play_media")
    events = []
    for naam in ("omi_listening", "omi_listening_done", "omi_conversation"):
        hass.bus.async_listen(naam, callback(lambda e: events.append((e.event_type, dict(e.data)))))
    runs = []

    async def nep_pipeline(hass, *, event_callback, stt_stream, pipeline_id, conversation_id, **kw):
        audio = b"".join([b async for b in stt_stream])
        runs.append((pipeline_id, conversation_id, len(audio)))
        event_callback(PipelineEvent(PipelineEventType.STT_END, {"stt_output": {"text": "hoe laat"}}))
        antwoord = "Welke kamer?" if wedervraag and len(runs) == 1 else "Tien uur."
        event_callback(PipelineEvent(PipelineEventType.INTENT_END, {"intent_output": {
            "conversation_id": "g1", "continue_conversation": False,
            "response": {"speech": {"plain": {"speech": antwoord}}}}}))
        event_callback(PipelineEvent(PipelineEventType.TTS_END, {"tts_output": {"url": "http://x/tts.mp3"}}))

    async def praat(n: int) -> None:
        while g._opname is None:
            await asyncio.sleep(0.01)
        for _ in range(n):
            g.audio(LUID)
        # daarna niets: de hanger zwijgt in stilte

    with (
        patch("custom_components.omi.gesprek.OpusDecoder", NepDecoder),
        patch("custom_components.omi.gesprek.async_pipeline_from_audio_stream", nep_pipeline),
        patch("custom_components.omi.spraak.STILTE_S", 0.2),
        patch("custom_components.omi.gesprek.NA_ANTWOORD_S", 0),
        patch("custom_components.omi.gesprek.NA_ANTWOORD_PER_TEKEN_S", 0),
        patch("custom_components.omi.gesprek.TRIL_NEGEER_S", 0),
    ):
        taak = hass.async_create_task(g.tik())
        await praat(50)
        if wedervraag:
            while not runs or g._opname is None:
                await asyncio.sleep(0.01)
            await praat(50)
        await asyncio.wait_for(taak, 5)
        await hass.async_block_till_done()

    assert runs[0][0] == "abc" and runs[0][1] is None
    assert runs[0][2] >= 50 * 640
    assert len(runs) == (2 if wedervraag else 1)
    if wedervraag:
        assert runs[1][1] == "g1"                  # vervolg in hetzelfde gesprek
    assert [c.data["entity_id"] for c in afspelen] == ["media_player.kamer"] * len(runs)
    assert afspelen[0].data["announce"] is True
    soorten = [e[0] for e in events]
    assert soorten[:3] == ["omi_listening", "omi_listening_done", "omi_conversation"]
    gesprek = events[2][1]
    assert gesprek["room"] == "Kamer" and gesprek["heard"] == "hoe laat" and gesprek["error"] == ""
    assert g.status == "idle"
    h.tril.assert_any_await(1, keer=2)


async def test_te_kort_en_fout(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: ADRES}, options={})
    h = OmiHanger(hass, ADRES, "Omi")
    h.codec = 21
    h.tril = AsyncMock()
    g = Gesprek(hass, entry, h)

    async def stuk(hass, **kw):
        raise RuntimeError("weg")

    with (
        patch("custom_components.omi.gesprek.OpusDecoder", NepDecoder),
        patch("custom_components.omi.gesprek.async_pipeline_from_audio_stream", stuk),
        patch("custom_components.omi.spraak.STILTE_S", 0.2),
    ):
        # Tweede tik zonder spraak: niets naar de pipeline.
        taak = hass.async_create_task(g.tik())
        while g._opname is None:
            await asyncio.sleep(0.01)
        await g.tik()
        await asyncio.wait_for(taak, 2)
        assert g.laatste_fout is None

        taak = hass.async_create_task(g.tik())
        while g._opname is None:
            await asyncio.sleep(0.01)
        for _ in range(50):
            g.audio(LUID)
        await asyncio.wait_for(taak, 5)
    assert g.laatste_fout == "RuntimeError: weg"
    h.tril.assert_awaited_with(3)
