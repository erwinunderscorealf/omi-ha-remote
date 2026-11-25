# Omi-hanger voor Home Assistant — handleiding

Koppelt een [Omi](https://www.omi.me/)-hanger aan Home Assistant. De Omi is een draagbare
microfoon met een knop en een trilmotor, die via Bluetooth (BLE) praat. De koppeling loopt
via de Bluetooth die Home Assistant al heeft.

*English: [README.md](README.md).*

> **Stand: meetversie 0.1.** De hanger verbindt, de knop werkt en de audiostroom wordt
> gemeten. Praten met je spraakassistent kan **nog niet**: dat komt in de volgende versie
> (zie [Wat komt er nog](#wat-komt-er-nog)). Met deze versie zie je of je Bluetooth-opstelling
> de audio van de hanger aankan.

## Hoe het werkt

```
 Omi-hanger ──BLE──▶ ontvanger ──▶ Home Assistant ──▶ deze integratie
 (microfoon,         (eigen adapter of                  │
  knop, trilmotor)    ESPHome Bluetooth-proxy)          ├─ sensoren: batterij, ontvanger, audiokwaliteit
                                                        └─ gebeurtenis: knopdrukken
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

Er is geen YAML-configuratie.

## Gebruiken

- **Eén keer tikken:** de hanger trilt kort. Dat bewijst dat Home Assistant hem via de
  huidige ontvanger bereikt. De gebeurtenis-entiteit *Knop* legt de tik vast.
- **Dubbel tikken / lang drukken:** komt ook op de entiteit *Knop*. Bruikbaar als trigger in
  automatiseringen (`event.<naam>_button`, attribuut `event_type`).
- **Hanger vrijgeven** (bijvoorbeeld voor de telefoon-app): zet de schakelaar *Verbinden*
  uit. Weer aan = opnieuw verbinden. De stand blijft bewaard na een herstart.

## Entiteiten

| Entiteit | Wat het zegt |
|---|---|
| Verbonden | De BLE-verbinding staat. Attribuut `last_error`: de laatste fout. |
| Ontvanger | Naam van de adapter of proxy die de verbinding draagt. Attribuut `source`: het adres. |
| Batterij | Batterijniveau van de hanger (elke 10 minuten gelezen). |
| Knop | Gebeurtenis: `single_tap`, `double_tap`, `long_press`. |
| Verbinden | Schakelaar: uit = hanger vrijgeven zonder Home Assistant te herstarten. |
| Audiopakketten | Pakketten per seconde over de laatste 5 s. Rond **50** is gezond. |
| Audioverlies | Verloren pakketten in %, uit gaten in de pakketnummers. |
| Verbindingen | Hoe vaak er (opnieuw) verbonden is. |
| Stilvallen | Hoe vaak de audio 5 s wegbleef en opnieuw verbinden nodig was. |
| Signaalsterkte | RSSI van de hanger (diagnostisch, standaard uit). |

### De metingen lezen

- *Audiopakketten* rond 50 en *Audioverlies* bijna 0 %: deze ontvanger kan de audio aan.
- Veel *Stilvallen* of hoog verlies bij één ontvanger: verplaats hem, zet er een proxy
  dichterbij, of kijk naar de wifi (een ESPHome-proxy stuurt de audio over wifi door).
- *Verbindingen* loopt snel op terwijl de hanger stil ligt: iets anders pakt de verbinding
  (vaak de telefoon-app), of de ontvanger heeft geen verbindingsplek meer vrij.

## Problemen oplossen

| Wat je ziet | Oorzaak en oplossing |
|---|---|
| Niet gevonden | Hanger uit, buiten bereik of verbonden met de telefoon. Maak hem los in de app. |
| Hanger knippert blauw-rood en verbindt niet | Hij houdt nog een oude verbinding vast, vaak met een computer waarop andere Omi-software draaide. Verbreek die daar (Linux: `bluetoothctl disconnect <adres>`) of zet de hanger uit en aan. |
| *Verbonden* springt aan en uit | Zwak signaal, of de ontvanger heeft geen verbindingsplek vrij. Kijk naar de sensor *Ontvanger* en de logs van de proxy. |
| Audiopakketten 0 bij elke herverbinding via een ESPHome-proxy | Opgelost in 0.1.1: de proxy sloeg met een servicecache de MTU-uitwisseling over, waardoor de MTU 23 bleef, te klein voor de audio. De integratie verbindt nu zonder servicecache (±2 s extra per verbinding). In het log moet bij "verbonden via … (codec …, mtu …)" een MTU boven 23 staan. |
| Audiopakketten 0, Stilvallen loopt op | Bekend gedrag van de hanger: de stroom stopt soms na 30-60 s. De integratie verbindt vanzelf opnieuw (±5 s). |

Uitgebreid loggen:

```yaml
action: logger.set_level
data:
  custom_components.omi: debug
```

**Instellingen → Apparaten en diensten → Omi pendant → ⋮ → Diagnostiek downloaden** geeft
een momentopname van alle tellers (het adres van de hanger is weggelaten).

## Wat komt er nog

Volgende versie, spraak:

1. Tikken → korte tril → de hanger luistert; stilte of een tweede tik sluit de vraag af.
2. De audio gaat door een **Assist-pipeline** naar keuze (spraak naar tekst,
   gespreksagent, tekst naar spraak).
3. Het antwoord klinkt op de speaker in de kamer van de ontvanger die de verbinding heeft
   (een tabel ontvanger → mediaspeler in de opties).
4. Stelt de assistent een wedervraag, dan trilt de hanger en luistert hij opnieuw, zonder tik.
5. Dubbeltik = nieuw gesprek; een lange tril betekent een fout.

## Licentie

[MIT](LICENSE). Omi is een product van Based Hardware; dit project staat daar los van.
