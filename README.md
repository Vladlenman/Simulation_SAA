# SAA-Simulation

Nachfolger des Excel-Werkzeugs `BM-Tool_PH_abgabe.xlsx`: Gewichte einer
strategischen Asset Allocation im Browser einstellen, die historische Wirkung
sofort sehen und **mehrere Gewichtungen nebeneinander vergleichen**.

Eine HTML-Oberfläche, die auf Python läuft. Keine Bloomberg-Verbindung nötig –
die Kursreihen sind aus dem Blatt `timeseries` übernommen.

---

## Schnellstart

**1. Herunterladen und entpacken.** Das ZIP irgendwohin entpacken, wo Sie
Schreibrechte haben – Dokumente oder Desktop genügt. **Wichtig: wirklich
entpacken**, nicht nur im ZIP hineinklicken; sonst findet Python die Daten
nicht.

**2. Python installieren**, falls noch nicht vorhanden: <https://www.python.org/downloads/>
Unter Windows beim Installieren **„Add Python to PATH" ankreuzen**.

**3. Starten** – Datei im entpackten Ordner doppelklicken:

| | Datei |
|---|---|
| Windows | `start-windows.bat` |
| macOS | `start-macos.command` |

Beim ersten Start wird `numpy` nachinstalliert, das dauert einen Moment. Danach
öffnet sich der Browser auf <http://127.0.0.1:8000/>. Das schwarze Fenster
bleibt offen, solange das Tool läuft – **zum Beenden einfach schließen** oder
`Strg+C` drücken.

<details>
<summary>Lieber von Hand über die Kommandozeile?</summary>

```bash
cd Pfad/zum/entpackten/Ordner
pip install numpy
python run.py
```

Unter Windows heißt es meist `py` statt `python`.
</details>

### Wenn etwas klemmt

| Meldung | Was zu tun ist |
|---|---|
| „Python wurde nicht gefunden" | Python fehlt oder steht nicht im PATH. Neu installieren und „Add Python to PATH" ankreuzen. |
| „numpy konnte nicht installiert werden" | Firmenrechner ohne Zugang zum Paketserver. Die IT um `pip install numpy` bitten – das ist die einzige Abhängigkeit. |
| macOS: „kann nicht geöffnet werden, da es von einem nicht verifizierten Entwickler stammt" | Rechtsklick auf die Datei → **Öffnen** → im Dialog nochmals **Öffnen**. Nur beim ersten Mal nötig. |
| macOS: Datei öffnet sich im Editor statt zu starten | Im Terminal einmal `chmod +x start-macos.command` ausführen. |
| „Address already in use" | Es läuft schon eine Instanz. Altes Fenster schließen, oder `python run.py --port 8080` verwenden. |
| Browser öffnet sich nicht von selbst | <http://127.0.0.1:8000/> von Hand im Browser eingeben. |

---

## Was es kann

* **Gewichte einstellen** für 12 Assetklassen, per Zahl oder Regler, mit
  Gruppensummen und Normierung auf 100 %.
* **Zwischen zwei Benchmark-Modi umschalten** (siehe unten) und beide direkt
  gegenüberstellen.
* **Benchmark je Assetklasse überschreiben** – pro Klasse ein Dropdown aus den
  verfügbaren Zeitreihen, das den Modus für diese eine Klasse aussticht.
* **Kennzahlen**: Total Return, Rendite p.a., Volatilität, Sharpe, Sortino,
  Max Drawdown mit Tief und Erholungsdauer, Calmar, bester/schlechtester
  Monat, Anteil positiver Monate, VaR und CVaR 95 %.
* **Verlauf**: indexierte Wertentwicklung (optional logarithmisch),
  Drawdown-Verlauf, rollierende 24-Monats-Rendite und -Volatilität.
* **Markowitz-Bullet**: Effizienzlinie (long only, voll investiert, optional
  mit Obergrenze je Klasse), Min-Varianz- und Max-Sharpe-Portfolio, die
  einzelnen Assetklassen und die eigenen Szenarien als Punkte.
* **Beiträge**: Performance- und Risikobeitrag je Assetklasse. Der
  Risikobeitrag zeigt, wo das Risiko wirklich herkommt – oft etwas ganz
  anderes als die Gewichte.
* **Korrelationsmatrix** der gewichteten Assetklassen.
* **Kalenderjahre** je Szenario, als Grafik und Tabelle.
* **Szenarien speichern und vergleichen**: jede Gewichtung lässt sich benennen
  und ablegen; angehakte Szenarien erscheinen in allen Auswertungen neben dem
  Entwurf, über einen gemeinsamen Zeitraum gerechnet.

Zwei Szenarien sind schon angelegt: die SAA aus der abgegebenen Excel-Datei und
die TAA von VG 3 aus dem Bewegungsmonitor.

---

## Installation

Gebraucht werden **Python 3.10+ und numpy**. Mehr nicht – kein Flask, kein
FastAPI, kein SciPy, keine Chart-Bibliothek, kein Internet. Das ist Absicht:
das Werkzeug soll auf einem Arbeitsplatzrechner ohne Installationsrechte
laufen.

```bash
pip install numpy          # openpyxl nur für einen Neuimport aus Excel
python run.py
```

Weitere Schalter:

```bash
python run.py --port 8080
python run.py --no-browser
```

---

## Daten aktualisieren

`data/monthly_returns.csv` ist die Datengrundlage: Monatsenden als `JJJJ-MM`,
eine Spalte je Zeitreihe, Renditen als Dezimalzahl.

Nach einer neuen Bloomberg-Abfrage reicht:

```bash
python tools/import_excel.py pfad/zur/neuen/BM-Tool.xlsx
```

Das liest das Blatt `timeseries` (die Hartkopie, kein Terminal nötig) und
schreibt CSV und Benchmark-Katalog neu. Einzelne Reihen lassen sich auch von
Hand in die CSV eintragen, siehe `docs/benchmark-mapping.md`.

---

## Stimmen die Zahlen?

Ja – nachgewiesen gegen die Excel-Datei selbst:

```bash
python tests/test_against_excel.py
```

Der Test rechnet die SAA der abgegebenen Datei mit ihren 15 Benchmarkzeilen und
1,09 % TER über 2003-02 bis 2025-12 und vergleicht mit den Werten aus
`BM-Tool!D34:I34`. Abweichung unter **1e-12** bei Total Return, Rendite p.a.,
Volatilität, Max Drawdown und Calmar Ratio. Ein zweiter Test macht dasselbe
über die Konfiguration im Modus `Geldmarkt + Aufschlag`, damit eine unbedachte
Änderung an `asset_classes.json` auffällt.

**Zwei Werte weichen bewusst ab:**

1. **Sharpe Ratio.** Die Excel-Datei weist 0,8285 aus, das Tool 0,36. Die
   Excel-Rechnung zieht den risikolosen Zins erst ab 2011-01 ab, davor ist die
   Spalte leer. Details in `docs/excel-workbook-notes.md`.
2. **Startzeitpunkt.** Die Excel-Datei beginnt bei 2003-02, weil die Formel
   erst in Zeile 28 anfängt – nicht weil Daten fehlen. Das Tool nutzt die
   volle Historie ab 2001-01, also 26 Monate mehr. Über das Feld "Start" lässt
   sich der alte Zeitraum jederzeit nachstellen.

---

## Die zwei Benchmark-Modi

Oben links im Bedienfeld steht ein Umschalter:

| Modus | Was passiert | Wofür |
|---|---|---|
| **Marktindizes** | jede Assetklasse auf einem echten Index | realistisches Risiko, belastbare Effizienzlinie |
| **Geldmarkt + Aufschlag** | `Anleihen HTM`, `Alternative Investments`, `Mikrofinanz` und `Immobilien` auf Geldmarktsatz + Aufschlag | Nachvollziehbarkeit gegenüber der Excel-Datei, längere Historie |

Der Umschalter betrifft **nur diese vier Klassen** – alle übrigen bleiben in
beiden Stellungen auf ihrem Marktindex. Der Modus wird **mit dem Szenario
gespeichert**, dieselben Gewichte lassen sich also zweimal ablegen und
vergleichen. Dafür gibt es auch den Knopf **"beide Modi vergleichen"**.

Was der Umschalter ausmacht, bei gleichen Gewichten und gleichem Zeitraum
(2004-09 bis 2026-01):

| Kennzahl | Marktindizes | Geldmarkt + Aufschlag |
|---|---|---|
| Volatilität p.a. | 3,15 % | 2,90 % |
| Sharpe Ratio | 0,37 | **0,47** |
| Max Drawdown | −10,46 % | −9,31 % |
| Max-Sharpe-Portfolio | 44 % HTM, 36 % Immobilien, 9 % Aktien Welt | **90 % Immobilien** |

`Geldmarkt + Aufschlag` ist eine nahezu gerade Linie ohne eigenes Risiko. Der
Optimierer sieht dort Rendite ohne Risiko und schiebt fast alles hinein – ein
Artefakt, kein Ergebnis. **Für jede Optimierung den Modus `Marktindizes`
verwenden.** Der Preis: die Auswertung beginnt erst 2004-09 statt 2001-01, weil
der Immobilienindex nicht weiter zurückreicht.

Der Geldmarktsatz wird exakt aus den Reihen der Excel-Datei zurückgerechnet
(`ESTR3MA (+100BP)` minus 100 bp), deshalb ist **jeder** Aufschlag
konfigurierbar, nicht nur 100/150/200 bp. `tests/` prüft das gegen die
Originalreihen.

⚠️ Zwei Klassen haben **auch im Modus `Marktindizes`** keinen echten Benchmark
und sind mit `PROXY` markiert:

* **`Mikrofinanz`** – es existiert keine Reihe. Einen Index gibt es über
  Bloomberg praktisch nicht; gangbar ist der NAV eines Mikrofinanzfonds über
  seine ISIN. Kandidaten in `docs/benchmark-mapping.md`.
* **`Anleihen HTM`** – zu fortgeführten Anschaffungskosten bewertet, ein
  Marktindex überzeichnet das Risiko. Dafür gibt es jetzt **`yield_curves`**:
  die Durchschnittsverzinsung des Buchs als Stützstellen, auch wenn sie sich
  über die Jahre geändert hat. Siehe **`docs/htm-buchrendite.md`**.

---

## Aufbau

```
start-windows.bat           Start per Doppelklick (Windows)
start-macos.command         Start per Doppelklick (macOS)
run.py                      Start über die Kommandozeile
config/asset_classes.json   Assetklassen, Benchmarks, beide Modi  <- hier anpassen
data/monthly_returns.csv    Monatsrenditen, aus timeseries
data/benchmarks.json        Katalog: Name, Währung, Historie
portfolios/*.json           gespeicherte Szenarien, eine Datei je Szenario
saa/data.py                 Laden von Zeitreihen und Konfiguration
saa/metrics.py              Kennzahlen
saa/portfolio.py            Gewichte -> Renditereihe, Beiträge
saa/frontier.py             Effizienzlinie
saa/store.py                Szenarien lesen/schreiben
saa/app.py                  HTTP-Server und JSON-API
templates/index.html        die Oberfläche
static/app.js               Bedienlogik
static/charts.js            Diagramme (eigenes SVG, damit offline nutzbar)
tools/import_excel.py       Neuimport aus einer BM-Tool-Datei
tests/                      Abgleich gegen die Excel-Werte
docs/                       Excel-Analyse, Benchmarks, HTM-Buchrendite
```

Gespeicherte Szenarien sind einzelne JSON-Dateien – versionierbar, per Mail
weitergebbar und auch ohne das Tool lesbar. Jede enthält Gewichte, TER,
Benchmark-Modus und etwaige Überschreibungen je Klasse.

---

## Rechenmodell

Monatlich rebalanciert, Kosten gleichmäßig über das Jahr verteilt:

```
r_Portfolio(t) = Σ w_i · r_Benchmark(i,t) − ((1 + TER)^(1/12) − 1)
```

* Der **Zeitraum** ist die Schnittmenge aller gewichteten Benchmarks. Eine
  Klasse mit kurzer Historie verkürzt also die Auswertung – das Tool sagt unter
  "Was den Zeitraum begrenzt", welche das ist.
* **Annualisiert** wird mit 12 Perioden, Volatilität als Stichprobe (n−1) –
  dieselbe Konvention wie in der Excel-Datei.
* **Sharpe und Sortino** laufen gegen `ECC0TR03 Index` (Euro Cash) über den
  gesamten Zeitraum.
* Die **Effizienzlinie** optimiert im Mean-Variance-Sinn auf arithmetische
  Erwartungswerte; angezeigt wird die geometrische Rendite p.a.
* Beim **Vergleich** werden alle Szenarien auf den gemeinsamen Zeitraum
  beschnitten.

---

## Offene Punkte

* **Echte Benchmarks** für `Mikrofinanz` und `Anleihen HTM`, siehe oben.
* **`OeKB-Daten` und `BONUS-Daten`** sind noch nicht eingebunden. Die Excel-Datei
  stellte der simulierten SAA die tatsächlich erzielte Performance (BONUS) und
  den Branchenschnitt (OeKB) gegenüber. Beides liegt als Monatsreihe vor und
  liesse sich als zwei weitere Vergleichslinien ergänzen – sagen Sie Bescheid,
  wenn das gebraucht wird.
* **Unter- und Obergrenzen je Klasse** für die Effizienzlinie gibt es bisher nur
  als eine gemeinsame Obergrenze. Pro Klasse ist im Backend schon vorgesehen
  (`bounds` in `/api/frontier`), in der Oberfläche aber noch nicht angelegt.
