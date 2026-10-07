# Anleihen HTM: eine Verzinsung, die sich über die Zeit ändert

## Warum kein Index passt

Ein HTM-Bestand wird **zu fortgeführten Anschaffungskosten** bewertet. Der
Marktpreis der Anleihen schwankt, die Bilanz nicht. Die Rendite des Buchs ist
deshalb keine Kursentwicklung, sondern eine **Verzinsung**: der Kupon, der
Monat für Monat anfällt.

Beide bisherigen Behelfe sind aus demselben Grund falsch, nur in
entgegengesetzte Richtungen:

| Behelf | Problem |
|---|---|
| Marktindex (`LE13TREU`, `LBEATREU`) | zeigt Kursschwankungen und Drawdowns, die im HTM-Buch nie auftreten – **überzeichnet** das Risiko |
| Geldmarkt + Aufschlag | eine Gerade, trifft weder die Höhe der Verzinsung noch ihre Veränderung – **unterzeichnet** es |

Zum Vergleich, jeweils 100 % „Anleihen HTM", volle Historie:

| Benchmark | Rendite p.a. | Vola p.a. | Max Drawdown |
|---|---|---|---|
| **HTM Buchrendite** (Beispielwerte) | 3,28 % | **0,29 %** | **0,00 %** |
| Geldmarkt + 100 bp | 2,57 % | 0,53 % | −0,07 % |
| `LE13TREU Index` (EuroAgg 1–3y) | 2,43 % | 1,40 % | −5,84 % |
| `LBEATREU Index` (Euro Aggregate) | 3,28 % | 4,02 % | **−19,54 %** |

Die letzte Zeile zeigt das Problem am deutlichsten: Rendite fast identisch mit
dem Buch, aber ein ausgewiesener Drawdown von fast 20 %, den es in der Bilanz
nie gegeben hat. Bei 35 % Portfoliogewicht verzerrt das jede Risikokennzahl.

---

## Die Lösung: ein Verzinsungspfad

Was sich bei einem HTM-Buch tatsächlich über die Jahre ändert, ist die
**Durchschnittsverzinsung**: alte Hochkuponanleihen laufen aus und werden zu
den jeweils aktuellen Sätzen ersetzt. Das Buch gleitet also langsam vom alten
Zinsniveau zum neuen – es springt nicht.

Genau das bildet der Block `yield_curves` in `config/asset_classes.json` ab:

```json
"yield_curves": {
  "HTM Buchrendite": {
    "label": "HTM-Buch, Durchschnittsverzinsung",
    "interpolate": true,
    "compounding": "geometric",
    "schedule": [
      { "from": "1998-07", "rate_pa": 0.050 },
      { "from": "2008-01", "rate_pa": 0.040 },
      { "from": "2016-01", "rate_pa": 0.024 },
      { "from": "2023-01", "rate_pa": 0.022 }
    ]
  }
}
```

Dann in der Klasse `Anleihen HTM`:

```json
"benchmark": "HTM Buchrendite",
"index_proxy": false
```

Fertig – die Reihe steht überall zur Verfügung: Kennzahlen, Beiträge,
Korrelationen, Effizienzlinie.

### Was die Felder bedeuten

| Feld | Bedeutung |
|---|---|
| `schedule` | Stützstellen. Jeder Eintrag gilt **ab** diesem Monat bis zum nächsten Eintrag; der letzte bis zum Ende der Daten. Vor dem ersten Eintrag gibt es keine Werte, die Klasse begrenzt dann den Auswertungszeitraum. |
| `rate_pa` | Verzinsung **pro Jahr als Dezimalzahl**: 0.045 = 4,5 % p.a. |
| `interpolate` | `true` lässt die Verzinsung zwischen den Stützstellen **linear wandern** – so verhält sich ein rollierendes Buch. `false` erzeugt Stufen: die Verzinsung springt am Stichtag. |
| `compounding` | `geometric` (Standard) rechnet `(1+rate)^(1/12)-1`, zwölf Monate ergeben also **exakt** die angegebene Jahresverzinsung. `simple` rechnet `rate/12` – die Konvention der Euribor-Reihen der Excel-Datei, aufgezinst kommt dabei etwas mehr heraus als angegeben (bei 4 % rund 7 bp). |
| `until` | optionales Ende, falls die Reihe nicht bis zum Schluss laufen soll. |

### Welche Zahlen Sie brauchen

Nur die **Durchschnittsverzinsung des HTM-Buchs zu einigen Stichtagen**. Eine
Stützstelle pro Jahr reicht völlig, bei trägen Büchern auch alle paar Jahre –
dazwischen interpoliert das Tool. Typische Quellen:

* der Rechenschaftsbericht bzw. die Bestandsliste je Jahresultimo,
* die Effektivverzinsung des Buchs aus dem Bestandsführungssystem,
* notfalls der durchschnittliche Kupon gewichtet nach Nominale.

Lieber grobe, echte Werte als ein exakter falscher Index.

### Zwei Beispiele

**Stufen** – die Verzinsung wird je Jahr festgeschrieben:

```json
"interpolate": false,
"schedule": [
  { "from": "2019-01", "rate_pa": 0.0215 },
  { "from": "2020-01", "rate_pa": 0.0198 },
  { "from": "2021-01", "rate_pa": 0.0181 },
  { "from": "2022-01", "rate_pa": 0.0176 }
]
```

**Gleitend** – nur die Wendepunkte, dazwischen interpoliert:

```json
"interpolate": true,
"schedule": [
  { "from": "1998-07", "rate_pa": 0.050 },
  { "from": "2021-06", "rate_pa": 0.018 },
  { "from": "2026-01", "rate_pa": 0.028 }
]
```

### Eine nützliche Eigenschaft

Mit `interpolate: true` ist die ausgewiesene Volatilität **nicht null**
(im Beispiel 0,29 % p.a.), obwohl es keine Kursschwankung gibt. Das ist kein
Fehler: die Schwankung kommt daher, dass sich die Verzinsung über die Zeit
verändert. Genau das ist das echte Risiko eines HTM-Buchs –
**Wiederanlagerisiko**, nicht Kursrisiko. Mit `interpolate: false` und
konstanten Sätzen wäre die Vola innerhalb jeder Stufe exakt null.

---

## Wenn Sie lieber eine fertige Monatsreihe haben

Falls das Bestandsführungssystem direkt Monatsrenditen liefert, geht es auch
ohne `yield_curves`: einfach eine Spalte in `data/monthly_returns.csv`
ergänzen (Kopfzeile = Name, Werte als Dezimalzahl) und diesen Namen als
`benchmark` eintragen. Der Weg über `yield_curves` ist nur bequemer, wenn Sie
eine Handvoll Zinssätze statt 300 Monatswerte haben.
