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
