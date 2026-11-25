# Omi pendant for Home Assistant

[![Validate](https://github.com/erwinunderscorealf/omi-ha-remote/actions/workflows/validate.yml/badge.svg)](https://github.com/erwinunderscorealf/omi-ha-remote/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)

Connects an [Omi](https://www.omi.me/) AI pendant (a wearable BLE microphone with a button
and a vibration motor) to Home Assistant, using Home Assistant's own Bluetooth stack.

*Nederlandse handleiding: [README.nl.md](README.nl.md).*

> **Status: measurement release 0.1.** The pendant connects, its button works and the
> audio stream is measured. It does **not** talk to your voice assistant yet: that comes
> in the next release (see [Roadmap](#roadmap)). Use this release to find out whether your
> Bluetooth setup can carry the pendant's audio.

## How it works

```
 Omi pendant ──BLE──▶ receiver ──▶ Home Assistant ──▶ this integration
 (microphone,         (local adapter or                  │
  button, vibration)   ESPHome Bluetooth proxy)          ├─ sensors: battery, receiver, audio quality
                                                         └─ event: button presses
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

There is no YAML configuration.

## Using it

- **Tap the button once:** the pendant vibrates briefly. That proves Home Assistant can
  reach it through the current receiver. The *Button* event entity records the press.
- **Double tap / long press:** recorded on the *Button* event entity. Use them as
  automation triggers (state of `event.<name>_button`, attribute `event_type`).
- **Release the pendant** (for instance to use the phone app): turn off the *Connect*
  switch. Turn it on again to reconnect. The switch keeps its position across restarts.

## Entities

| Entity | What it tells you |
|---|---|
| Connected | The BLE connection is up. Attribute `last_error`: the last failure, if any. |
| Receiver | Name of the adapter or proxy carrying the connection. Attribute `source`: its address. |
| Battery | Battery level of the pendant (read every 10 minutes). |
| Button | Event entity: `single_tap`, `double_tap`, `long_press`. |
| Connect | Switch: off releases the pendant without restarting Home Assistant. |
| Audio packets | Audio packets per second over the last 5 s. About **50** is healthy. |
| Audio loss | Lost audio packets in %, from gaps in the packet numbers. Attributes: totals. |
| Connections | How often the integration (re)connected. |
| Audio stalls | How often the audio stream stopped for 5 s and a reconnect was needed. |
| Signal strength | RSSI of the pendant's advertisements (diagnostic, disabled by default). |

### Reading the measurements

- *Audio packets* around 50 and *Audio loss* near 0 %: this receiver carries the audio
  fine. Voice will work through it.
- Many *Audio stalls* or high loss on one receiver: move it, add a proxy closer by, or check
  its Wi-Fi (ESPHome proxies forward the audio over Wi-Fi).
- *Connections* rising fast while the pendant stays put: something else keeps taking the
  connection (often the phone app), or the receiver has no free connection slot.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Not discovered | The pendant is off, out of range, or connected to the phone. Disconnect it from the app. |
| Pendant blinks blue and red, never connects | It still holds an old connection, often to a computer that ran other Omi software. Disconnect it there (Linux: `bluetoothctl disconnect <address>`) or switch the pendant off and on. |
| *Connected* flips on and off | Weak signal, or the receiver ran out of connection slots. Check the *Receiver* sensor and the proxy's logs. |
| Audio packets 0 on every reconnect through an ESPHome proxy | Fixed in 0.1.1: the proxy skipped the MTU exchange when it reused cached services, leaving MTU 23, too small for the audio. The integration now connects without the service cache (about 2 s extra per connection). With debug logging, the line "verbonden via … (codec …, mtu …)" should show an MTU above 23. |
| Audio packets 0, stalls rising | Known pendant behaviour: the stream sometimes stops after 30–60 s; the integration reconnects automatically (about 5 s). |

Debug logging:

```yaml
action: logger.set_level
data:
  custom_components.omi: debug
```

**Settings → Devices & services → Omi pendant → ⋮ → Download diagnostics** gives a snapshot
of all counters (the pendant's address is redacted).

## Roadmap

Next release, voice:

1. Tap → short vibration → the pendant listens; silence or a second tap ends the question.
2. The audio goes through an **Assist pipeline** of your choice (speech-to-text,
   conversation agent, text-to-speech).
3. The answer plays on the speaker of the room whose receiver carries the connection
   (a receiver → media player table in the options).
4. When the assistant asks a question back, the pendant vibrates and listens again
   without a tap.
5. Double tap starts a new conversation; a long vibration signals an error.

## Development

Tests use [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component):

```bash
pip install pytest-homeassistant-custom-component
pytest
```

## License

[MIT](LICENSE). Omi is a product of Based Hardware; this project is not affiliated with them.
