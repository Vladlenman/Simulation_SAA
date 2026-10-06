# Was die Blätter der alten BM-Tool-Datei tun

Bestandsaufnahme von `BM-Tool_PH_abgabe.xlsx`, erstellt beim Nachbau. Grundlage
für die Entscheidung, was ins Python-Tool übernommen wurde und was nicht.

| Blatt | Zweck | Im neuen Tool |
|---|---|---|
| `FLDS` | Parameter der Bloomberg-Abfrage | nur dokumentiert |
| `BB_basicdata` | Stammdaten, live aus Bloomberg | – |
| `basicdata` | Hartkopie derselben Stammdaten | ja, als Benchmark-Katalog |
| `BB_timeseries` | Kursreihen, live aus Bloomberg | – |
| `timeseries` | Hartkopie der Kursreihen | **ja, die Datengrundlage** |
| `TReuters Global Hedged` | Wandelanleihen-Index, nicht in Bloomberg | ja, über `timeseries` |
| `TER_PK` | Kostensätze je VRG/VG | ja, als TER-Eingabe |
| `OeKB-Daten` | OeKB-Vergleichsindizes | noch nicht |
| `BONUS-Daten` | Ist-Performance der Veranlagungsgemeinschaften | noch nicht |
| `BM-Tool` | die eigentliche Rechnung | **ja, komplett** |
| `BM-Drawdowns` | Hilfsblatt für Drawdown-Grafiken | ja, als Berechnung |
| `Bewegungsmonitor` | Gewichte je VRG/VG und Exposure-Übersicht | als Quelle für Szenarien |

---

## Die Blätter im Einzelnen

### `FLDS` – die Bloomberg-Abfrage
Fünf Zellen, die steuern, **wie** die Kursreihen gezogen werden:

| Feld | Wert | Bedeutung |
|---|---|---|
| Wert | `DAY_TO_DAY_TOT_RETURN_GROSS_DVDS` | Total Return inkl. Dividenden |
| Startdatum | 01.01.1900 | so früh wie möglich |
| Enddatum | 14.07.2026 | Ende der Abfrage |
| Periodizität | `cm` | calendar month, also Monatsende |

Dieses Blatt wird **nur gebraucht, wenn neu aus Bloomberg gezogen wird**. Für
die Auswertung ist es ohne Funktion.

### `BB_basicdata` / `basicdata` – welche Indizes
Beide haben dieselben Spalten (Ticker, Währung, Name, Historienbeginn …).
Der Unterschied:

* **`BB_basicdata`** enthält die *lebenden* Bloomberg-Formeln. Ohne Terminal
  steht dort überall `#NAME?` – genau das sieht man in der abgegebenen Datei.
* **`basicdata`** ist die **eingefrorene Kopie** mit den Werten.

Für die Auswertung zählt also nur `basicdata`. Es ist die Liste "welche
Zeitreihe gibt es, in welcher Währung, ab wann". Genau dafür wird es im neuen
Tool verwendet: `data/benchmarks.json`.

Dasselbe Paar gibt es bei den Kursen: **`BB_timeseries`** (live) und
**`timeseries`** (Hartkopie).

### `timeseries` – die Datengrundlage
Spaltenpaare: ungerade Spalte = Datum **und** in Zeile 1 der Name der Reihe,
gerade Spalte = Monatsrendite **in Prozent**. Jede Reihe hat ihre eigene
Datumsspalte, weil die Historien unterschiedlich weit zurückreichen.

Zwei Reihen ohne Daten (`JPCAEU1Y`, `JGAGGUSD`) haben einen Header, aber eine
kaputte Abfrage. Sie werden beim Import übersprungen.

### `TReuters Global Hedged`
Der Thomson-Reuters-Wandelanleihenindex (EUR hedged). Er ist **nicht über
Bloomberg verfügbar**, deshalb als Tageswerte hinterlegt und rechts daneben auf
Monatsrenditen verdichtet. Diese Monatsreihe steht dann als
`Convertibles Index EUR` auch in `timeseries`.

### `TER_PK` – wofür es gebraucht wird
Das Blatt beantwortet eine einzige Frage: **welcher Kostensatz wird vom
Bruttoertrag abgezogen?**

* Links (A:D): je VRG/VG der individuelle TER und die OeKB-Klasse.
* Mitte (F:I): je OeKB-Klasse der Mittelwert, der **Median** und ein
  Pauschalwert.

`BM-Tool` nutzt es zweistufig:

```
B30 = VLOOKUP(B29; TER_PK!A:C; 3)    -> OeKB-Klasse der gewählten VRG
B31 = VLOOKUP(B30; TER_PK!F2:I7; 3)  -> Median-TER dieser Klasse
```

Bei `VG 3` kommt so `VK (OeKB)` → **1,09 % p.a.** heraus. Dieser Satz geht als
`((1+TER)^(1/12)-1)` in **jede** Monatsrendite ein.

Für das neue Tool heißt das: **`TER_PK` ist eine Nachschlagetabelle für eine
einzige Zahl.** Darum ist die TER im Python-Tool ein direktes Eingabefeld – man
kann den Wert aus `TER_PK` eintragen, muss aber nicht.

### `OeKB-Daten` und `BONUS-Daten`
Beides Vergleichsreihen, Monatsrenditen ab 1998:

* **`OeKB-Daten`**: die OeKB-Vergleichsindizes (`VK`, `PK defensiv`,
  `PK konservativ`, `PK ausgewogen`, `PK aktiv`, `PK dynamisch`) plus
  Anleihen-, Aktien- und Immobilienquoten der Branche.
* **`BONUS-Daten`**: die **tatsächlich erzielte** Performance je VRG/VG.

In `BM-Tool` landen sie in den Spalten AQ (BONUS) und AU (OeKB) und liefern die
zwei Vergleichslinien neben der simulierten SAA. Also: *simuliert* gegen
*tatsächlich erzielt* gegen *Branchenschnitt*.

Diese beiden Reihen sind im Python-Tool **noch nicht** eingebunden – siehe
"Offene Punkte" in der README.

### `Bewegungsmonitor` – Ihre Frage, was die Tabellen zeigen

Das Blatt hat **zwei getrennte Tabellen**, die nichts miteinander zu tun haben.

**Tabelle 1 (Zeilen 3–27): die Gewichte je Veranlagungsgemeinschaft.**
Pro VRG/VG vier Spalten:

| Spalte | Bedeutung |
|---|---|
| `TAA` | taktische Allokation, der **Ist-Stand** |
| `SAA` | strategische Allokation, der **Zielwert** |
| `SW OG` | Schwankungsbreite **Obergrenze** |
| `SW UG` | Schwankungsbreite **Untergrenze** |

Die Zeilen sind die Anlagekategorien, mit Zwischensummen (`Aktien`,
`Anleihen`, `Plus Investments`, `Cash`) und `Summe` = 100 %. Spalte A ordnet
jede Zeile einer Assetklasse des BM-Tools zu.

Oben in Zeile 1–2 steht, **welche Spalte dieses Blattes das BM-Tool liest**:
`Spalte SAA = L`, `Spalte TAA = E` für VG 1 usw. Deshalb die `INDIRECT`-Formel
in `BM-Tool!E4`. Das Blatt ist also die **Eingabemaske für die Gewichte** – die
Rolle, die im neuen Tool die Regler links übernehmen.

Beachtenswert: die TAA ist feiner aufgeteilt als die SAA (z. B. `MSCI World`
und `MSCI World MinVol` getrennt), und bei einigen VRGs summiert die TAA nicht
exakt auf 100 % (VRG 12: 98,96 %).

**Tabelle 2 (Zeilen 35–39): wie das Exposure zustande kommt.**
Hier geht es nicht um Assetklassen, sondern um **vier Risikofaktoren**:

| Zeile | Faktor |
|---|---|
| `Aktien` | Aktienquote |
| `Duration` | Zinsrisiko |
| `Credit (Non-IG)` | Nicht-Investmentgrade-Anteil |
| `FX` | offene Fremdwährung |

und je Faktor vier Spalten:

| Spalte | Bedeutung |
|---|---|
| `TAA` | Exposure aus der Allokation |
| `Kassa` | Gegenposition über Kassainstrumente |
| `Derivate` | Gegenposition über Derivate |
| `gesamt` | was netto übrig bleibt |

Beispiel VG 3: Aktien `TAA 15,8 %`, `Kassa −9,7 %`, `Derivate −2,9 %`,
`gesamt 3,3 %`. Das Blatt zeigt also, **wie weit das Exposure abgesichert
ist**, inklusive der Limits in Spalte A/B (`FX-Anteil QMV (max 30 %)`).

Diese zweite Tabelle ist reines Risiko-Reporting auf den **Ist-Bestand** und
hat mit der historischen Simulation nichts zu tun. Deshalb ist sie **nicht**
ins Python-Tool übernommen worden – für eine SAA-Simulation gibt es dort keine
Kassa- und Derivatepositionen.

### `BM-Tool` – die eigentliche Rechnung
Von links nach rechts:

| Bereich | Inhalt |
|---|---|
| A3:J19 | Assetklassen, Benchmark, SAA- und TAA-Gewicht, Beiträge |
| L3:M12 | Gewichtssummen je Assetklasse |
| P2:T22 | eine 2×2-Kovarianz-Spielerei (nicht an die Rechnung angeschlossen) |
| V3:AL302 | **das Herz**: Datumsraster + Monatsrendite je Benchmark |
| AM:AP | Portfolio: Rendite, Excess, Wertverlauf, Drawdown |
| AQ:AX | dieselben vier Spalten für BONUS und OeKB |
| A33:M51 | Kennzahlenblöcke (ab Start, gemeinsamer Zeitraum, YTD) |
| A57:B62 | Performance Contribution |
| A64:L104 | Risk Contribution über die 15×15-Kovarianzmatrix |
| AY:FA | gewichtete Einzelreihen, Wertverläufe, Drawdowns je Assetklasse |

Die Portfoliorendite steht in `AM`:

```
AM28 = MMULT(W28:AK28; D4:D18) − ((1+B31)^(1/12)−1)
```

also Skalarprodukt aus Monatsrenditen und SAA-Gewichten, minus anteilige
Kosten. Genau diese Formel rechnet das Python-Tool – nachgewiesen in
`tests/test_against_excel.py`.

---

## Zwei Fehler, die beim Nachbau aufgefallen sind

### 1. Die Sharpe Ratio stimmt nicht

`BM-Tool!G34` rechnet die Sharpe Ratio über die Spalte `AN` (Excess Return):

```
AN28 = IF(AM28=0; 0; AM28 − $AL28)
```

`AL` soll den risikolosen Zins (`ECC0TR03 Index`) enthalten – **ist aber erst
ab Zeile 123, also ab 2011-01, befüllt.** Davor ist die Spalte leer und `AN`
übernimmt die Bruttorendite.

Die ausgewiesene Sharpe Ratio von **0,8285** ist damit ein Mischwert: 2003-02
bis 2010-12 ohne Zinsabzug, ab 2011-01 mit. Sauber gerechnet über den
risikolosen Zins der ganzen Periode ergibt sich **0,36**.

> Alle anderen Kennzahlen der Excel-Datei sind korrekt und werden vom Python-Tool
> auf 12 Nachkommastellen exakt reproduziert.

### 2. Der Startzeitpunkt 2003-02 ist willkürlich

`J34` sucht die erste Zeile mit einer Rendite ≠ 0 und findet Zeile 28. Der
Grund ist aber **nicht**, dass vorher Daten fehlen: in `AM3:AM27` steht schlicht
**keine Formel**. Die Daten reichen bis **2001-01** zurück, das sind
**26 zusätzliche Monate**, die der Auswertung bisher fehlen.

Das neue Tool bestimmt den Start aus der Datenlage und nutzt die volle
Historie – auf Wunsch lässt sich der Zeitraum im Feld "Start" von Hand
einschränken.

---

## Was bewusst nicht übernommen wurde

* **Externe Verknüpfungen** (`[3]`, `[4]`, `[5]`): mehrere Zellen, u. a. die
  Benchmark-Zuordnung in `C4:C18` und `H44`, zeigen auf Dateien, die nicht
  mitgeliefert wurden. Die Werte sind eingefroren, die Formeln tot. Im neuen
  Tool steht diese Zuordnung in `config/asset_classes.json`.
* **Der 2×2-Kovarianzblock in `P2:T22`**: eine Nebenrechnung mit zwei
  Gewichten (0,6 / 0,4), die an keiner Ausgabe hängt.
* **`B65:P65` und `B67`** referenzieren teils `#REF!` bzw. feste Zeilenbereiche
  (`W3:W203`), die nicht zum Auswertungszeitraum passen.
* **Die YTD-Blöcke für 2016/2017** (`A43:M51`) mit fest verdrahteten
  Startzeilen 183/195. Im neuen Tool gibt es stattdessen die vollständige
  Kalenderjahrestabelle.
