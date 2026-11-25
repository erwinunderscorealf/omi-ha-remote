# Omi pendant for Home Assistant

[![Validate](https://github.com/erwinunderscorealf/omi-ha-remote/actions/workflows/validate.yml/badge.svg)](https://github.com/erwinunderscorealf/omi-ha-remote/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)

Connects an [Omi](https://www.omi.me/) AI pendant (a wearable BLE microphone with a button
and a vibration motor) to Home Assistant, using Home Assistant's own Bluetooth stack.

*Nederlandse handleiding: [README.nl.md](README.nl.md).*

> **Status: 0.2, first voice release.** Tap the pendant, ask a question, and the answer
> from your Assist pipeline plays on the speaker of the room you are in. Tested in one
> household so far; reports are welcome.

## How it works

```
 Omi pendant ──BLE──▶ receiver ──▶ Home Assistant ──▶ this integration
 (microphone,         (local adapter or                  │
  button, vibration)   ESPHome Bluetooth proxy)          ├─ Assist pipeline → answer on that room's speaker
                                                         └─ sensors, button event, events
```

- **No extra hardware or app.** The integration uses the Bluetooth adapters and
  [ESPHome Bluetooth proxies](https://esphome.io/components/bluetooth_proxy.html) that
  Home Assistant already knows. Home Assistant picks the receiver with the best signal.
- **It follows the wearer.** When the connection drops (out of range, or the audio stream
  stalls), the integration reconnects in the background, through whichever receiver now
  hears the pendant best. The *Receiver* sensor shows which one carries the connection, so
  you can see the pendant move from room to room.
- **It never blocks Home Assistant.** Connecting happens in the background with a growing
  wait between attempts (5 s up to 60 s). Startup does not wait for the pendant.
- **One connection at a time.** The pendant accepts a single BLE connection. While Home
  Assistant holds it, the Omi phone app cannot connect, and the other way round.

## Requirements

- Home Assistant 2025.6 or newer, with the Bluetooth integration set up.
- An [Assist pipeline](https://www.home-assistant.io/voice_control/) with speech-to-text and
  text-to-speech, and a media player per room for the answers.
- A Bluetooth adapter or ESPHome Bluetooth proxy within reach of the pendant, able to make
  **active connections** (for proxies: `bluetooth_proxy: active: true`). Each pendant
  permanently uses one connection slot on the receiver that carries it.
- An Omi pendant (tested: Omi CV 1, firmware 3.0.21), disconnected from the Omi phone app.

## Installation

### Through HACS (recommended)

1. HACS → **Integrations** → menu ⋮ → **Custom repositories**.
2. Repository `https://github.com/erwinunderscorealf/omi-ha-remote`, type **Integration** →
   **Add**.
3. Search for **Omi pendant** → **Download**.
4. Restart Home Assistant.

### Manually

Copy `custom_components/omi/` from this repository to `/config/custom_components/omi/`
and restart Home Assistant.

## Setup

1. Switch the pendant on and disconnect it from the Omi phone app (or switch off Bluetooth
   on the phone).
2. Home Assistant discovers it by itself: **Settings → Devices & services** shows
   *Discovered: Omi*. Click **Add**.
   If it does not show up: **Add integration → Omi pendant** and choose it from the list.
3. Give it a name. The name sets the entity ids: with the name *Omi Anna* you get
   `sensor.omi_anna_battery`, `binary_sensor.omi_anna_connected`, and so on.
4. Optionally assign the device to an area.
5. On the integration, choose **Configure**: pick the **Assist pipeline**. Then pick a
   receiver under **Set up receiver**, choose its speaker (and optionally a room name) and
   submit. Repeat per receiver; submit with the receiver field empty to save.

There is no YAML configuration.

## Using it

- **Tap once, then talk.** One short vibration: it listens (the 0.4 s before the tap are
  included). Stop talking for 1.2 s, or tap again: two short vibrations, and the question
  goes to the pipeline. The answer plays on the speaker set for the receiver that carries
  the connection, so it follows you from room to room. A question lasts at most 15 s.
- **Follow-up:** when the assistant asks something back (the answer ends in "?", or the
  agent wants to continue), the pendant vibrates after the answer and listens for 6 s
  without a tap.
- **Double tap:** start a new conversation (two vibrations). **Long vibration:** something
  went wrong; see the *Assistant* sensor, attribute `error`.
- Every press is also recorded on the *Button* event entity, for your own automations
  (state of `event.<name>_button`, attribute `event_type`). A long press does nothing else.
- **Release the pendant** (for instance to use the phone app): turn off the *Connect*
  switch. Turn it on again to reconnect. The switch keeps its position across restarts.

## Entities

| Entity | What it tells you |
|---|---|
| Assistant | `idle`, `listening`, `processing` or `responding`. Attributes `heard`, `answer`, `error`: the last question. |
| Connected | The BLE connection is up. Attribute `last_error`: the last failure, if any. |
| Receiver | Name of the adapter or proxy carrying the connection. Attribute `source`: its address. |
| Battery | Battery level of the pendant (read every 10 minutes). |
| Button | Event entity: `single_tap`, `double_tap`, `long_press`. |
| Connect | Switch: off releases the pendant without restarting Home Assistant. |
| Audio packets | Audio packets per second over the last 5 s. About **50** while the pendant hears sound; 0 in silence. |
| Audio loss | Lost audio packets in %, from gaps in the packet numbers. Attributes: totals. |
| Connections | How often the integration (re)connected. |
| Audio stalls | How often the audio stream stopped for at least 5 s. Usually just silence: see below. |
| Signal strength | RSSI of the pendant's advertisements (diagnostic, disabled by default). |

### Events

For automations, for instance to duck music while the pendant listens:

| Event | When | Data |
|---|---|---|
| `omi_listening` | The pendant starts listening. | `room`, `device_id` |
| `omi_listening_done` | Speech-to-text is done, or there was nothing to send. | `room` |
| `omi_conversation` | After every question. | `room`, `wake_word` (`omi`), `heard`, `answer`, `error`, `device_id` |

`room` is the room name set for the receiver under *Configure* (default: the receiver's name).

### Reading the measurements

- The pendant only streams when it hears sound (voice detection in its firmware). Test
  with someone talking near it. *Audio packets* around 50 and *Audio loss* near 0 %: this receiver carries the audio
  fine. Voice will work through it.
- High loss on one receiver: move it, add a proxy closer by, or check
  its Wi-Fi (ESPHome proxies forward the audio over Wi-Fi).
- *Connections* rising fast while the pendant stays put: something else keeps taking the
  connection (often the phone app), or the receiver has no free connection slot.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Two vibrations, no answer | The question was shorter than 0.3 s, no speaker is set for the current receiver (warning in the log), or the answer was a bare "OK". Check *Configure* and the *Receiver* sensor. |
| Long vibration | The pipeline failed, or the pendant does not send Opus: attribute `error` of the *Assistant* sensor. |
| Not discovered | The pendant is off, out of range, or connected to the phone. Disconnect it from the app. |
| Pendant blinks blue and red, never connects | It still holds an old connection, often to a computer that ran other Omi software. Disconnect it there (Linux: `bluetoothctl disconnect <address>`) or switch the pendant off and on. |
| *Connected* flips on and off | Weak signal, or the receiver ran out of connection slots. Check the *Receiver* sensor and the proxy's logs. |
| Audio packets 0 | Normal in silence: the pendant only sends audio while it hears sound, and can stay quiet for minutes. Talk near it. Since 0.1.2 silence no longer triggers a reconnect. |
| Audio packets stay 0 while you talk | Check the MTU in the debug line "verbonden via … (codec …, mtu …)". An Opus packet needs more than 23; 0.1.1 connects without the service cache for that reason. |
| Audio packets far below 50 while you talk | The debug log shows per 5 s: notifications/s, bytes/s, length per notification and the share of fragments. Short notifications (≤20 bytes) and many fragments = small MTU: the pendant splits every audio frame. Since 0.1.3 the integration asks a local adapter for the real MTU (before, it always showed 23). |

Debug logging:

```yaml
action: logger.set_level
data:
  custom_components.omi: debug
```

**Settings → Devices & services → Omi pendant → ⋮ → Download diagnostics** gives a snapshot
of all counters (the pendant's address is redacted).

## Roadmap

- Listing in the HACS default store.
- A wake word instead of a tap (the audio is already there).

## Development

Tests use [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component):

```bash
pip install pytest-homeassistant-custom-component av hassil home-assistant-intents \
    pymicro-vad pyspeex-noise mutagen ha-ffmpeg
pytest
```

## License

[MIT](LICENSE). Omi is a product of Based Hardware; this project is not affiliated with them.
