# Omi-hanger voor Home Assistant — handleiding

Koppelt een [Omi](https://www.omi.me/)-hanger aan Home Assistant. De Omi is een draagbare
microfoon met een knop en een trilmotor, die via Bluetooth (BLE) praat. De koppeling loopt
via de Bluetooth die Home Assistant al heeft.

*English: [README.md](README.md).*

> **Stand: 0.2, eerste spraakversie.** Tik op de hanger, stel je vraag, en het antwoord van
> je Assist-pipeline klinkt op de speaker in de kamer waar je bent. Tot nu toe in één
> huishouden getest; ervaringen zijn welkom.

## Hoe het werkt

```
 Omi-hanger ──BLE──▶ ontvanger ──▶ Home Assistant ──▶ deze integratie
 (microfoon,         (eigen adapter of                  │
  knop, trilmotor)    ESPHome Bluetooth-proxy)          ├─ Assist-pipeline → antwoord op de speaker van die kamer
                                                        └─ sensoren, knop, events
```

- **Geen extra hardware of app.** De integratie gebruikt de Bluetooth-adapters en
  [ESPHome Bluetooth-proxy's](https://esphome.io/components/bluetooth_proxy.html) die Home
  Assistant al kent. Home Assistant kiest de ontvanger met het sterkste signaal.
- **Hij loopt mee.** Valt de verbinding weg (buiten bereik, of de audio stopt), dan verbindt
  de integratie op de achtergrond opnieuw, via de ontvanger die de hanger nu het best hoort.
  De sensor *Ontvanger* laat zien welke dat is: zo zie je de hanger van kamer naar kamer gaan.
- **Home Assistant wacht nooit op de hanger.** Verbinden gebeurt op de achtergrond, met een
  steeds langere pauze tussen pogingen (5 tot 60 s).
- **Eén verbinding tegelijk.** De hanger accepteert maar één BLE-verbinding. Zolang Home
  Assistant hem heeft, kan de Omi-app op de telefoon er niet bij, en andersom.

## Wat je nodig hebt

- Home Assistant 2025.6 of nieuwer, met de Bluetooth-integratie ingesteld.
- Een [Assist-pipeline](https://www.home-assistant.io/voice_control/) met spraak-naar-tekst en
  tekst-naar-spraak, en per kamer een mediaspeler voor de antwoorden.
- Een Bluetooth-adapter of ESPHome-proxy binnen bereik die **actief kan verbinden** (bij een
  proxy: `bluetooth_proxy: active: true`). Elke hanger houdt vast één verbindingsplek bezet op
  de ontvanger die hem draagt.
- Een Omi-hanger (getest: Omi CV 1, firmware 3.0.21), los van de Omi-app.

## Installeren

### Via HACS (aanbevolen)

1. HACS → **Integraties** → menu ⋮ → **Aangepaste repositories**.
2. Repository `https://github.com/erwinunderscorealf/omi-ha-remote`, type **Integratie** →
   **Toevoegen**.
3. Zoek **Omi pendant** → **Downloaden**.
4. Herstart Home Assistant.

### Met de hand

Kopieer `custom_components/omi/` uit deze repository naar `/config/custom_components/omi/`
en herstart Home Assistant.

## Instellen

1. Zet de hanger aan en maak hem los van de Omi-app (of zet Bluetooth op de telefoon uit).
2. Home Assistant vindt hem zelf: onder **Instellingen → Apparaten en diensten** staat
   *Ontdekt: Omi*. Klik **Toevoegen**.
   Verschijnt hij niet: **Integratie toevoegen → Omi pendant** en kies hem uit de lijst.
3. Geef hem een naam. Die bepaalt de entiteiten: met de naam *Omi Anna* krijg je
   `sensor.omi_anna_battery`, `binary_sensor.omi_anna_connected`, enzovoort.
4. Zet het apparaat eventueel in een ruimte.
5. Kies bij de integratie **Configureren**: kies de **Assist-pipeline**. Kies daarna onder
   **Ontvanger instellen** een ontvanger, wijs de speaker aan (en eventueel een ruimtenaam)
   en verstuur. Herhaal dat per ontvanger; verstuur met een leeg ontvangerveld om op te slaan.

Er is geen YAML-configuratie.

## Gebruiken

- **Eén keer tikken, dan praten.** Eén korte tril: hij luistert (de 0,4 s vóór de tik gaan
  mee). Zwijg 1,2 s of tik nog eens: twee korte trillen, en de vraag gaat naar de pipeline.
  Het antwoord klinkt op de speaker van de ontvanger die de verbinding draagt, dus het loopt
  met je mee van kamer naar kamer. Een vraag duurt hooguit 15 s.
- **Wedervraag:** vraagt de assistent iets terug (het antwoord eindigt op "?", of de agent
  wil doorpraten), dan trilt de hanger na het antwoord en luistert hij 6 s zonder tik.
- **Dubbel tikken:** nieuw gesprek (twee trillen). **Lange tril:** er ging iets mis; zie de
  sensor *Assistent*, attribuut `error`.
- Elke druk komt ook op de entiteit *Knop*, voor eigen automatiseringen
  (`event.<naam>_button`, attribuut `event_type`). Lang drukken doet verder niets.
- **Hanger vrijgeven** (bijvoorbeeld voor de telefoon-app): zet de schakelaar *Verbinden*
  uit. Weer aan = opnieuw verbinden. De stand blijft bewaard na een herstart.

## Entiteiten

| Entiteit | Wat het zegt |
|---|---|
| Assistent | Rust, luistert, denkt na of antwoordt (`idle`, `listening`, `processing`, `responding`). Attributen `heard`, `answer`, `error`: de laatste vraag. |
| Verbonden | De BLE-verbinding staat. Attribuut `last_error`: de laatste fout. |
| Ontvanger | Naam van de adapter of proxy die de verbinding draagt. Attribuut `source`: het adres. |
| Batterij | Batterijniveau van de hanger (elke 10 minuten gelezen). |
| Knop | Gebeurtenis: `single_tap`, `double_tap`, `long_press`. |
| Verbinden | Schakelaar: uit = hanger vrijgeven zonder Home Assistant te herstarten. |
| Audiopakketten | Pakketten per seconde over de laatste 5 s. Rond **50** zolang de hanger geluid hoort; 0 in stilte. |
| Audioverlies | Verloren pakketten in %, uit gaten in de pakketnummers. |
| Verbindingen | Hoe vaak er (opnieuw) verbonden is. |
| Stilvallen | Hoe vaak de audio minstens 5 s ophield. Meestal gewoon stilte: zie hieronder. |
| Signaalsterkte | RSSI van de hanger (diagnostisch, standaard uit). |

### Events

Voor automatiseringen, bijvoorbeeld om muziek zachter te zetten zolang de hanger luistert:

| Event | Wanneer | Data |
|---|---|---|
| `omi_listening` | De hanger begint te luisteren. | `room`, `device_id` |
| `omi_listening_done` | Spraakherkenning is klaar, of er was niets te versturen. | `room` |
| `omi_conversation` | Na elke vraag. | `room`, `wake_word` (`omi`), `heard`, `answer`, `error`, `device_id` |

`room` is de ruimtenaam die onder *Configureren* bij de ontvanger staat (standaard de naam van de ontvanger).

### De metingen lezen

- De hanger stuurt alleen audio als hij geluid hoort (spraakdetectie in de firmware). Test
  met iemand die in de buurt praat. *Audiopakketten* rond 50 en *Audioverlies* bijna 0 %: deze ontvanger kan de audio aan.
- Hoog verlies bij één ontvanger: verplaats hem, zet er een proxy
  dichterbij, of kijk naar de wifi (een ESPHome-proxy stuurt de audio over wifi door).
- *Verbindingen* loopt snel op terwijl de hanger stil ligt: iets anders pakt de verbinding
  (vaak de telefoon-app), of de ontvanger heeft geen verbindingsplek meer vrij.

## Problemen oplossen

| Wat je ziet | Oorzaak en oplossing |
|---|---|
| Twee trillen, geen antwoord | De vraag was korter dan 0,3 s, er is geen speaker ingesteld voor de huidige ontvanger (waarschuwing in het log), of het antwoord was een kaal "Oké". Kijk bij *Configureren* en naar de sensor *Ontvanger*. |
| Lange tril | De pipeline faalde, of de hanger stuurt geen Opus: attribuut `error` van de sensor *Assistent*. |
| Niet gevonden | Hanger uit, buiten bereik of verbonden met de telefoon. Maak hem los in de app. |
| Hanger knippert blauw-rood en verbindt niet | Hij houdt nog een oude verbinding vast, vaak met een computer waarop andere Omi-software draaide. Verbreek die daar (Linux: `bluetoothctl disconnect <adres>`) of zet de hanger uit en aan. |
| *Verbonden* springt aan en uit | Zwak signaal, of de ontvanger heeft geen verbindingsplek vrij. Kijk naar de sensor *Ontvanger* en de logs van de proxy. |
| Audiopakketten 0 | Normaal in stilte: de hanger stuurt alleen audio als hij geluid hoort, en kan minutenlang zwijgen. Praat in de buurt. Sinds 0.1.2 is stilte geen reden meer om opnieuw te verbinden. |
| Audiopakketten blijft 0 terwijl je praat | Kijk naar de MTU in de debugregel "verbonden via … (codec …, mtu …)". Een Opus-pakket heeft meer dan 23 nodig; 0.1.1 verbindt daarom zonder servicecache. |
| Audiopakketten ver onder 50 terwijl je praat | Debuglog per 5 s: notificaties/s, bytes/s, lengte per notificatie en het aandeel fragmenten. Korte notificaties (≤20 bytes) en veel fragmenten = kleine MTU: de hanger knipt elk audioframe op. Sinds 0.1.3 vraagt de integratie de echte MTU op bij een lokale adapter (voorheen stond daar altijd 23). |

Uitgebreid loggen:

```yaml
action: logger.set_level
data:
  custom_components.omi: debug
```

**Instellingen → Apparaten en diensten → Omi pendant → ⋮ → Diagnostiek downloaden** geeft
een momentopname van alle tellers (het adres van de hanger is weggelaten).

## Wat komt er nog

- Aanmelden bij de standaardlijst van HACS.
- Een wekwoord in plaats van tikken (de audio is er al).

## Licentie

[MIT](LICENSE). Omi is een product van Based Hardware; dit project staat daar los van.
