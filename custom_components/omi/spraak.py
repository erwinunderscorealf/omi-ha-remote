"""Audio van de hanger: Opus decoderen en bepalen wanneer de spreker klaar is."""

from __future__ import annotations

import time

import numpy as np

from .const import DREMPEL, MAX_S, MIN_SPRAAK_S, NEGEER_S, RATE, STILTE_S


class OpusDecoder:
    """Opus-frames van de hanger → 16 kHz 16-bit mono PCM.

    Gebruikt PyAV (FFmpeg), dat Home Assistant al meelevert. FFmpeg decodeert Opus
    altijd naar 48 kHz float; de resampler zet dat terug naar wat de pipeline wil.
    """

    def __init__(self) -> None:
        import av  # noqa: PLC0415 - pas laden als er gesproken wordt

        self._av = av
        self._ctx = av.CodecContext.create("opus", "r")
        self._ctx.sample_rate = RATE
        self._ctx.layout = "mono"
        self._resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)

    def decode(self, frame: bytes) -> bytes:
        uit = bytearray()
        try:
            for f in self._ctx.decode(self._av.Packet(frame)):
                for g in self._resampler.resample(f):
                    uit += bytes(g.planes[0])[: g.samples * 2]
        except self._av.FFmpegError:
            return b""
        return bytes(uit)


class Opname:
    """Houdt PCM bij en bepaalt met een vaste energiedrempel wanneer de spreker klaar is."""

    def __init__(self, voorloop: bytes = b"", wacht_s: float | None = None) -> None:
        self.pcm = bytearray(voorloop)
        self.start = time.monotonic()
        self.spraak_s = 0.0
        self.stilte_s = 0.0
        self.negeer_s = NEGEER_S      # tik- of trilgeluid aan het begin
        self.wacht_s = wacht_s        # vervolg zonder tik: opgeven als er niets komt
        self.laatst = self.start      # tijd van de laatste audio

    def voeg_toe(self, pcm: bytes) -> None:
        self.laatst = time.monotonic()
        self.pcm.extend(pcm)
        a = np.frombuffer(pcm, dtype=np.int16)
        if not a.size:
            return
        duur = a.size / RATE
        if self.negeer_s > 0:
            self.negeer_s -= duur
            return
        rms = float(np.sqrt(np.mean(a.astype(np.float64) ** 2)))
        if rms > DREMPEL:
            self.spraak_s += duur
            self.stilte_s = 0.0
        else:
            self.stilte_s += duur

    def klaar(self) -> str | None:
        """Waarom de opname af is, of None. Roep ook aan als er geen audio binnenkomt:
        de hanger stuurt in stilte niets (spraakdetectie in de firmware), dus ook het
        wegblijven van audio telt als stilte."""
        nu = time.monotonic()
        verstreken = nu - self.start
        stil = self.stilte_s + max(0.0, nu - self.laatst - 0.1)
        if verstreken >= MAX_S:
            return "max"
        if self.wacht_s and self.spraak_s < MIN_SPRAAK_S and verstreken >= self.wacht_s:
            return "geen antwoord"
        if self.spraak_s >= MIN_SPRAAK_S and stil >= STILTE_S:
            return "stilte"
        return None

    @property
    def duur_s(self) -> float:
        return len(self.pcm) / 2 / RATE
