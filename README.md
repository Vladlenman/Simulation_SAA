# SAA-Simulation

Nachfolger des Excel-Werkzeugs `BM-Tool_PH_abgabe.xlsx`: Gewichte einer
strategischen Asset Allocation im Browser einstellen, die historische Wirkung
sofort sehen und **mehrere Gewichtungen nebeneinander vergleichen**.

Eine HTML-Oberfläche, die auf Python läuft. Keine Bloomberg-Verbindung nötig –
die Kursreihen sind aus dem Blatt `timeseries` übernommen.

```
python run.py
```

öffnet <http://127.0.0.1:8000/>.

---

## Was es kann

* **Gewichte einstellen** für 12 Assetklassen, per Zahl oder Regler, mit
  Gruppensummen und Normierung auf 100 %.
* **Benchmark je Assetklasse wählen** – pro Klasse ein Dropdown aus den
  verfügbaren Zeitreihen.
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
Volatilität, Max Drawdown und Calmar Ratio.

**Zwei Werte weichen bewusst ab:**

1. **Sharpe Ratio.** Die Excel-Datei weist 0,8285 aus, das Tool 0,36. Die
   Excel-Rechnung zieht den risikolosen Zins erst ab 2011-01 ab, davor ist die
   Spalte leer. Details in `docs/excel-workbook-notes.md`.
2. **Startzeitpunkt.** Die Excel-Datei beginnt bei 2003-02, weil die Formel
   erst in Zeile 28 anfängt – nicht weil Daten fehlen. Das Tool nutzt die
   volle Historie ab 2001-01, also 26 Monate mehr. Über das Feld "Start" lässt
   sich der alte Zeitraum jederzeit nachstellen.

---

## ⚠️ Vier Assetklassen haben noch keinen echten Benchmark

`Anleihen HTM`, `Alternative Investments`, `Mikrofinanz` und `Immobilien`
laufen – wie schon in der Excel-Datei – auf **Euribor 3M + Aufschlag**. Das ist
eine fast gerade Linie ohne Risiko. Volatilität, Sharpe Ratio und vor allem die
Effizienzlinie fallen dadurch zu gut aus: das Max-Sharpe-Portfolio landet bei
über 90 % Immobilien, weil der Optimierer dort Rendite ohne Risiko sieht.

Das Tool kennzeichnet diese Klassen überall mit `PROXY`.
**`docs/benchmark-mapping.md` listet auf, welche Reihen gebraucht werden** und
welche brauchbaren Alternativen schon in den Daten liegen.

---

## Aufbau

```
run.py                      Start
config/asset_classes.json   Assetklassen und ihre Benchmarks  <- hier anpassen
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
docs/                       Analyse der Excel-Datei, Benchmark-Zuordnung
```

Gespeicherte Szenarien sind einzelne JSON-Dateien – versionierbar, per Mail
weitergebbar und auch ohne das Tool lesbar.

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

* **Echte Benchmarks** für die vier Platzhalterklassen, siehe oben.
* **`OeKB-Daten` und `BONUS-Daten`** sind noch nicht eingebunden. Die Excel-Datei
  stellte der simulierten SAA die tatsächlich erzielte Performance (BONUS) und
  den Branchenschnitt (OeKB) gegenüber. Beides liegt als Monatsreihe vor und
  liesse sich als zwei weitere Vergleichslinien ergänzen – sagen Sie Bescheid,
  wenn das gebraucht wird.
* **Unter- und Obergrenzen je Klasse** für die Effizienzlinie gibt es bisher nur
  als eine gemeinsame Obergrenze. Pro Klasse ist im Backend schon vorgesehen
  (`bounds` in `/api/frontier`), in der Oberfläche aber noch nicht angelegt.
