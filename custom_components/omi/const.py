"""Constanten voor de Omi-integratie."""

DOMAIN = "omi"

AUDIO_CHAR = "19b10001-e8f2-537e-4f6c-d104768a1214"
CODEC_CHAR = "19b10002-e8f2-537e-4f6c-d104768a1214"
KNOP_CHAR = "23ba7925-0000-1000-7450-346eac492e92"
HAPTIEK_CHAR = "cab1ab96-2ea5-4f4d-bb56-874b72cfc984"
BATTERIJ_CHAR = "00002a19-0000-1000-8000-00805f9b34fb"

# Knopnotificatie: uint32 LE.
KNOP_GEBEURTENIS = {1: "single_tap", 2: "double_tap", 3: "long_press"}

MEETVENSTER_S = 5          # statistiek en waakhond: zo vaak meten
BATTERIJ_ELKE_S = 600
WACHT_MIN_S = 5
WACHT_MAX_S = 60

# ---- spraak -----------------------------------------------------------------

OPUS_CODECS = (20, 21)     # 21 = Opus 16 kHz mono, 20 ms-frames
RATE = 16000
VOORLOOP_PAKKETTEN = 20    # 0,4 s audio van vóór de tik meenemen
MAX_S = 15.0               # langste vraag
DREMPEL = 250.0            # rms: stilte 15-50, spraak 400-1600 (gemeten op de hanger)
NEGEER_S = 0.5             # tikgeluid van de knop (rms 2000-4000) niet als spraak tellen
STILTE_S = 1.2             # zoveel stilte na spraak = klaar
MIN_SPRAAK_S = 0.3
VERVOLG_WACHT_S = 6.0      # na een wedervraag zo lang wachten op een antwoord
TRIL_NEGEER_S = 0.8        # trilgeluid aan het begin van een vervolgopname
PIPELINE_TIMEOUT_S = 120
# Pas luisteren als het antwoord is uitgesproken; anders hoort de hanger de speaker.
NA_ANTWOORD_S = 2.5
NA_ANTWOORD_PER_TEKEN_S = 0.06

CONF_PIPELINE = "pipeline"
CONF_ONTVANGERS = "receivers"   # {scanner-bron: {"speaker": entity_id, "room": naam}}
CONF_ONTVANGER = "receiver"
CONF_SPEAKER = "speaker"
CONF_RUIMTE = "room"
PIPELINE_VOORKEUR = "preferred"

# Events op de bus van Home Assistant (bijvoorbeeld om muziek te dempen of te loggen).
EVENT_LUISTERT = "omi_listening"
EVENT_LUISTEREN_KLAAR = "omi_listening_done"
EVENT_GESPREK = "omi_conversation"
