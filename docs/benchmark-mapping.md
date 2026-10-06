# Benchmark je Assetklasse – Stand und offene Punkte

Die Zuordnung steht in `config/asset_classes.json` und lässt sich dort ändern,
ohne Code anzufassen. In der Oberfläche ist je Klasse zusätzlich ein Dropdown
mit den Alternativen.

## Aktuelle Zuordnung

| # | Assetklasse | Benchmark | Reihe ab | Status |
|---|---|---|---|---|
| 1 | Anleihen EURO | `LBEATREU Index` – Bloomberg Euro Aggregate | 1998-07 | ✅ echt |
| 2 | Anleihen HTM | `ESTR3MA Index (+ 100BP)` – Euribor 3M + 1 % | 2001-01 | ⚠️ **Platzhalter** |
| 3 | Geldmarkt | `DBDCONIA Index` – EONIA/€STR Total Return | 1999-01 | ✅ echt |
| 4 | Anleihen Welt | `LEGATRUU Index` – Bloomberg Global Aggregate | 1990-02 | ✅ echt |
| 5 | Wandelanleihen (EUR hedged) | `Convertibles Index EUR` – T&R Global Convertibles hedged | 1993-12 | ✅ echt |
| 6 | Rohstoffe | `BCOMDET Index` – Bloomberg Commodity TR EUR hedged | 2001-05 | ✅ echt |
| 7 | Aktien Welt | `MSDEWIN Index` – MSCI World Net TR | 1999-01 | ✅ echt |
| 8 | Aktien Europa (EUR hedged) | `NDDLE15 Index` – MSCI Europe Net TR Local | 1970-02 | ✅ echt |
| 9 | Aktien EM | `MSDEEEMN Index` – MSCI EM Net TR EUR | 2001-01 | ✅ echt |
| 10 | Alternative Investments | `ESTR3MA Index (+ 100BP)` | 2001-01 | ⚠️ **Platzhalter** |
| 11 | Mikrofinanz | `ESTR3MA Index (+ 100BP)` | 2001-01 | ⚠️ **Platzhalter** |
| 12 | Immobilien | `ESTR3MA Index (+ 200BP)` | 2001-01 | ⚠️ **Platzhalter** |

Diese Zuordnung ist **aus der alten Datei übernommen** (`BM-Tool!C4:C18`), mit
drei Änderungen:

* `Anleihen HTM` und `Geldmarkt` sind **getrennt**. In der Excel-Datei waren sie
  eine Zeile (`Anleihen HTM / Geldmarkt`) mit einem gemeinsamen Benchmark.
* `Rohstoffe` hat jetzt einen Benchmark. In der Excel-Datei gab es die Klasse in
  der Gewichtsliste (`L8`), aber keine zugeordnete Zeitreihe – ein Gewicht > 0
  hätte dort nichts bewirkt.
* `Geldmarkt` liegt auf `DBDCONIA` statt auf `Euribor + Aufschlag`.

---

## ⚠️ Das Problem mit den vier Platzhaltern

Vier Assetklassen laufen auf **`Euribor 3M + Aufschlag`**. Das ist kein Index,
sondern eine **fast gerade Linie**: ein Geldmarktsatz plus konstantem Spread.

Die Folgen sind messbar und gehen in eine Richtung – alles sieht zu gut aus:

| Kennzahl | `Immobilien` laut Platzhalter | realistisch für offene Immobilienfonds |
|---|---|---|
| Volatilität p.a. | **0,53 %** | 1–4 % |
| Max Drawdown | praktisch 0 | −10 % und mehr |
| Risikobeitrag im Portfolio | **0,00 %** bei 9 % Gewicht | deutlich positiv |

Im Tab **Beiträge** sieht man das direkt: `Anleihen HTM` (35 % Gewicht!),
`Alternative Investments`, `Mikrofinanz` und `Immobilien` tragen zusammen
**0,00 %** zum Risiko bei, liefern aber fast die Hälfte der Performance.

**Für die Effizienzlinie ist das fatal.** Der Optimierer sieht eine Anlage mit
Rendite ohne Risiko und schiebt alles hinein: das Max-Sharpe-Portfolio landet
bei **92,7 % Immobilien** mit einer Sharpe Ratio von 1,9. Das ist kein
Ergebnis, das ist ein Artefakt des Platzhalters.

Das Tool weist deshalb an drei Stellen darauf hin: ein `PROXY`-Badge neben dem
Regler, ein Warnhinweis über jeder Auswertung und eine Fußnote am Bullet.

### Was gebraucht wird

Für diese vier Klassen wären echte Monatsreihen (Total Return, EUR, möglichst
ab 2001) nötig. Vorschläge, falls Sie die Wahl haben:

| Klasse | Möglicher echter Benchmark |
|---|---|
| **Anleihen HTM** | Da HTM zu fortgeführten Anschaffungskosten bewertet wird, ist eine Marktreihe systematisch falsch. Sinnvoller: eine **konstante Verzinsung aus der tatsächlichen Durchschnittsrendite des HTM-Buchs**. Die Blätter `VG1 HTM Index` / `VG2 HTM Index` in `timeseries` tun genau das (0,036 % bzw. 2,3 % p.a. konstant) und stehen im Dropdown zur Wahl. Nötig wäre der für Ihr Buch passende Satz. |
| **Immobilien** | `CPBRLET AV Equity` (LLB Semper Real Estate, ab 2004-09) liegt schon in den Daten und ist im Dropdown. Alternativ ein offener Immobilienfondsindex oder MSCI/INREV. |
| **Alternative Investments** | `NEIXCTA Index` (SG CTA, ab 2000-01) liegt schon in den Daten und ist im Dropdown – passt, wenn AI im Wesentlichen CTA/Multi-Asset ist. Für ein breiteres Mandat eher HFRI oder Credit Suisse Hedge Fund Index. |
| **Mikrofinanz** | Hier gibt es **gar keine** Reihe. Üblich sind SMX (Symbiotics Microfinance Index) oder der NAV-Verlauf des konkret gehaltenen Fonds. Die Spalte `Mikrofinanz` in `timeseries` ist **eine exakte Kopie von `LET1TREU Index`** (EuroAgg Treasury 1–3y) – also auch nur ein Platzhalter, kein Mikrofinanzdatum. |

**Sagen Sie mir, welche davon Sie beschaffen können** (oder liefern Sie die
Monatsreihen als CSV) – das Eintragen ist dann eine Zeile pro Klasse in
`config/asset_classes.json`.

---

## Eine neue Zeitreihe aufnehmen

1. Spalte in `data/monthly_returns.csv` ergänzen. Kopfzeile = Name der Reihe,
   eine Zeile je Monat im Format `JJJJ-MM`, Werte als **Dezimalzahl**
   (0,0125 für 1,25 %), leere Zelle wo keine Daten.
2. In `config/asset_classes.json` bei der Klasse `benchmark` auf den neuen
   Namen setzen und `"proxy": false` eintragen.
3. Browser neu laden – die Konfiguration wird bei jedem Aufruf frisch gelesen.

Kommt die Reihe aus einer neuen Bloomberg-Abfrage, einfacher:
`python tools/import_excel.py pfad/zur/neuen/BM-Tool.xlsx` erzeugt die CSV neu.

---

## Weitere verfügbare Reihen

Diese liegen in den Daten und sind über das Dropdown oder die Konfiguration
nutzbar:

`BCEX6T` · `BCOMTR` (Commodity TR unhedged) · `BEHLTREU` (Euro High Yield) ·
`ECC0TR03` (Euro Cash, der risikolose Zins) · `ESTR3MA (+150BP)` ·
`JPEIDHEU` (JPM EMBIG Diversified) · `LCEMTRUU` (EM Local Currency) ·
`LE13TREU` (EuroAgg 1–3y) · `LECPTREU` (Euro Corporate) ·
`LEEGTREU` (Euro Government) · `MSDEE15N` (MSCI Europe EUR) ·
`MSDEEMUN` (MSCI EMU) · `MSDEWEUN` (MSCI World EUR) ·
`MXWOHEUR` (MSCI World 100 % hedged EUR) · `NDEEWNR` (MSCI AC World) ·
`NDUEEGF` (MSCI EM USD) · `SPGSUETR` (S&P GSCI Ultra-Light Energy) ·
`TReuters Global Hedged` (Wandelanleihen, endet 2017-12)
