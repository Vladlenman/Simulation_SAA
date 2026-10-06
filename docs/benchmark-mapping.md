# Benchmark je Assetklasse – die zwei Modi

Die Zuordnung steht in `config/asset_classes.json` und lässt sich dort ändern,
ohne Code anzufassen.

In der Oberfläche gibt es oben links einen Umschalter mit zwei Stellungen. Er
betrifft **nur die vier Klassen**, die in der Excel-Datei auf
`Euribor + Aufschlag` liefen; alle übrigen bleiben in beiden Modi auf ihrem
Marktindex.

| Modus | Was passiert | Wofür |
|---|---|---|
| **Marktindizes** | jede Klasse auf einem echten Index | realistisches Risiko, ehrliche Korrelationen, belastbare Effizienzlinie |
| **Geldmarkt + Aufschlag** | die vier Klassen auf Geldmarktsatz + Aufschlag | Nachvollziehbarkeit gegenüber der Excel-Datei und längere Historie |

Der Modus wird **mit dem Szenario gespeichert**. Dieselben Gewichte lassen sich
also zweimal ablegen und direkt gegenüberstellen – dafür gibt es auch den Knopf
**"beide Modi vergleichen"**.

---

## Die Zuordnung im Einzelnen

| Assetklasse | Modus *Marktindizes* | ab | Modus *Geldmarkt + Aufschlag* |
|---|---|---|---|
| Anleihen EURO | `LBEATREU Index` – Euro Aggregate | 1998-07 | gleich |
| **Anleihen HTM** | `LE13TREU Index` – EuroAgg 1–3y ⚠️ | 1998-07 | `Geldmarkt + 100 bp` ⚠️ |
| Geldmarkt | `DBDCONIA Index` – EONIA/€STR TR | 1999-01 | gleich |
| Anleihen Welt | `LEGATRUU Index` – Global Aggregate | 1990-02 | gleich |
| Wandelanleihen (EUR hedged) | `Convertibles Index EUR` | 1993-12 | gleich |
| Rohstoffe | `BCOMDET Index` – BBG Commodity TR EUR hedged | 2001-05 | gleich |
| Aktien Welt | `MSDEWIN Index` – MSCI World Net TR | 1999-01 | gleich |
| Aktien Europa (EUR hedged) | `NDDLE15 Index` – MSCI Europe Net TR Local | 1970-02 | gleich |
| Aktien EM | `MSDEEEMN Index` – MSCI EM Net TR | 2001-01 | gleich |
| **Alternative Investments** | `NEIXCTA Index` – SG CTA | 2000-01 | `Geldmarkt + 100 bp` ⚠️ |
| **Mikrofinanz** | `LET1TREU Index` – EA Tsy 1–3y ⚠️ | 1998-07 | `Geldmarkt + 100 bp` ⚠️ |
| **Immobilien** | `CPBRLET AV Equity` – LLB Semper Real Estate | 2004-09 | `Geldmarkt + 200 bp` ⚠️ |

⚠️ = Behelf, kein echter Benchmark für diese Klasse. Die Oberfläche markiert das
mit `PROXY`; `MODUS` kennzeichnet die vier Klassen, die am Umschalter hängen.

Gegenüber der Excel-Datei zusätzlich geändert:

* `Anleihen HTM` und `Geldmarkt` sind **getrennt** (vorher eine Zeile).
* `Rohstoffe` hat **erstmals** einen Benchmark – in der Excel-Datei gab es die
  Klasse in der Gewichtsliste, aber keine Zeitreihe dazu.

---

## Was der Umschalter praktisch ausmacht

Gleiche Gewichte (die SAA der Excel-Datei), gleicher Zeitraum 2004-09 bis
2026-01, 257 Monate:

| Kennzahl | Marktindizes | Geldmarkt + Aufschlag | Differenz |
|---|---|---|---|
| Rendite p.a. | 2,40 % | 2,61 % | +0,21 pp zu hoch |
| Volatilität p.a. | 3,15 % | 2,90 % | −0,25 pp zu niedrig |
| Sharpe Ratio | 0,37 | 0,47 | **+0,10 zu gut** |
| Max Drawdown | −10,46 % | −9,31 % | 1,15 pp zu mild |
| Erholung nach 2022 | 37 Monate | 23 Monate | 14 Monate zu optimistisch |

Deutlicher noch an der Effizienzlinie:

| | Marktindizes | Geldmarkt + Aufschlag |
|---|---|---|
| Max-Sharpe-Portfolio | 44 % HTM, 36 % Immobilien, 9 % Aktien Welt | **90 % Immobilien** |
| erreichte Sharpe Ratio | 0,92 | 1,81 |

Im Modus *Geldmarkt + Aufschlag* sieht der Optimierer bei Immobilien Rendite
ohne Risiko und schiebt fast alles dorthin. Das ist kein Ergebnis, sondern ein
Artefakt des Behelfs-Benchmarks. **Für jede Optimierung also den Modus
*Marktindizes* verwenden.**

Der Preis des realistischen Modus: die Auswertung beginnt erst **2004-09**
statt 2001-01, weil der Immobilienindex nicht weiter zurückreicht. Das Tool
sagt unter "Was den Zeitraum begrenzt", welche Klasse gerade bremst.

---

## Wie der Geldmarktsatz erzeugt wird

Die Reihen `ESTR3MA (+100BP)`, `(+150BP)` und `(+200BP)` aus der Excel-Datei
unterscheiden sich auf **1e-19 genau** um `Aufschlag / 12` pro Monat. Daraus
lässt sich der reine Basissatz exakt zurückrechnen:

```
Basissatz(t) = ESTR3MA(+100BP)(t) − 0,0100 / 12
Geldmarkt + n bp(t) = Basissatz(t) + n / 10 000 / 12
```

Deshalb ist **jeder** Aufschlag möglich, nicht nur 100/150/200 bp. Im Feld
`key_rate_spread_bp` je Klasse lässt sich der Wert frei setzen – etwa 150 bp
für Immobilien statt 200 bp. `tests/test_against_excel.py` prüft, dass die so
erzeugten Reihen mit den Originalen der Excel-Datei übereinstimmen.

---

## Was noch fehlt

Zwei Klassen haben **auch im Modus *Marktindizes*** keinen echten Benchmark:

| Klasse | Lage | Was helfen würde |
|---|---|---|
| **Mikrofinanz** | Es gibt gar keine Reihe. `LET1TREU` (EA Tsy 1–3y) ist nur ein Platzhalter mit ähnlicher Schwankungsbreite. Die Spalte `Mikrofinanz` der Excel-Datei war eine **exakte Kopie genau dieser Reihe**. | SMX (Symbiotics Microfinance Index) oder der NAV-Verlauf des gehaltenen Fonds |
| **Anleihen HTM** | Hier ist das Problem grundsätzlich: HTM wird zu fortgeführten Anschaffungskosten bewertet. Ein Marktindex zeigt eine Schwankung, die in der Bilanz nie auftritt – er **überzeichnet** das Risiko, so wie der Geldmarktsatz es unterzeichnet. | die tatsächliche Durchschnittsverzinsung des HTM-Buchs als konstante Reihe. `VG1/VG2 HTM Index` im Dropdown tun genau das (0,036 % bzw. 2,3 % p.a.); gebraucht wird der für Ihr Buch passende Satz |

Für `Immobilien` und `Alternative Investments` ist der Fall mit `CPBRLET` und
`NEIXCTA` erst einmal gelöst. Falls Sie bessere Reihen haben – ein offener
Immobilienfondsindex, MSCI/INREV, HFRI –, lässt sich das in einer Zeile tauschen.

---

## Eine neue Zeitreihe aufnehmen

1. Spalte in `data/monthly_returns.csv` ergänzen: Kopfzeile = Name der Reihe,
   eine Zeile je Monat als `JJJJ-MM`, Werte als **Dezimalzahl** (0,0125 für
   1,25 %), leere Zelle wo keine Daten.
2. In `config/asset_classes.json` bei der Klasse `benchmark` auf den neuen Namen
   setzen und `index_proxy` entfernen bzw. auf `false`.
3. Browser neu laden – die Konfiguration wird bei jedem Aufruf frisch gelesen.

Aus einer neuen Bloomberg-Abfrage geht es in einem Schritt:

```bash
python tools/import_excel.py pfad/zur/neuen/BM-Tool.xlsx
```

---

## Weitere verfügbare Reihen

Über das Dropdown je Klasse oder die Konfiguration nutzbar:

`BCEX6T` · `BCOMTR` (Commodity TR unhedged) · `BEHLTREU` (Euro High Yield) ·
`ECC0TR03` (Euro Cash, der risikolose Zins) · `JPEIDHEU` (JPM EMBIG
Diversified) · `LCEMTRUU` (EM Local Currency) · `LE13TREU` (EuroAgg 1–3y) ·
`LECPTREU` (Euro Corporate) · `LEEGTREU` (Euro Government) · `MSDEE15N`
(MSCI Europe EUR) · `MSDEEMUN` (MSCI EMU) · `MSDEWEUN` (MSCI World EUR) ·
`MXWOHEUR` (MSCI World 100 % hedged EUR) · `NDEEWNR` (MSCI AC World) ·
`NDUEEGF` (MSCI EM USD) · `SPGSUETR` (S&P GSCI Ultra-Light Energy) ·
`TReuters Global Hedged` (Wandelanleihen, endet 2017-12) · `VG1/VG2 HTM Index`
(konstante HTM-Verzinsung) · `Geldmarkt`, `Geldmarkt + 100 bp`,
`Geldmarkt + 200 bp` (synthetisch)
