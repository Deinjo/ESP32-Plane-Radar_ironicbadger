# GetRoadsAndWaterForPlaneRadar

Diese Toolchain laedt Strassen- und Wassergeometrien aus OpenStreetMap ueber
die Overpass API, reduziert sie fuer ein rundes 240x240-Pixel-Display und
erzeugt C++-Header sowie SVG-Vorschauen.

Das Beispiel verwendet den bisherigen Radar-Mittelpunkt:

```text
Breitengrad: 51.48415698
Laengengrad: 7.41573987
```

## Voraussetzungen

- Python 3.9 oder neuer
- Internetzugang fuer die Overpass-Abfragen
- PowerShell oder eine andere Konsole

Es werden keine externen Python-Pakete benoetigt. Die Skripte verwenden die
Python-Standardbibliothek.

## Verzeichnis

Die Befehle werden aus diesem Ordner ausgefuehrt:

```powershell
cd C:\Projekte\GitHub\ESP32-Plane-Radar_ironicbadger\tools\GetRoadsAndWaterForPlaneRadar
```

Die wichtigen Unterordner sind:

```text
input\          Eingabedateien, zum Beispiel MapCities.cpp
data\           heruntergeladene Overpass-Daten
display_output\ generierte Header und SVG-Dateien
```

`data\` und `display_output\` koennen vor einem neuen Lauf geloescht werden.
Beide Ordner werden von den Skripten bei Bedarf neu angelegt.

## 1. Strassen laden

Der folgende Aufruf laedt Autobahnen und Bundesstrassen im Radius von 52 km.
Die Koordinaten sind der Mittelpunkt des Suchbereichs.

```powershell
python .\download_a1_motorways.py `
    --radius 29990 `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --include-federal-roads `
    --output-dir .\data
```

Ohne `--include-federal-roads` werden nur Autobahnen geladen. Mit dem Parameter
werden zusaetzlich B-Referenzen und die OSM-Typen `trunk` und `primary`
beruecksichtigt.

Der Downloader arbeitet mit:

- `overpass-api.de` als bevorzugtem Server
- `overpass.kumi.systems` als Fallback
- bis zu zehn Versuchen pro Server
- automatischem Wechsel bei temporaeren Serverfehlern

Die wichtigsten Optionen sind:

```text
--radius       Radius in Metern
--latitude     Mittelpunkt-Breitengrad
--longitude    Mittelpunkt-Laengengrad
--output-dir   Zielordner fuer die einzelnen Strassendateien
--motorway     optional nur eine A- oder B-Strasse, zum Beispiel A45 oder B224
--include-trunk A-Korridore mit highway=trunk zusaetzlich laden
--include-federal-roads A- und B-Referenzen mit motorway/trunk/primary laden
```

Beispiel fuer eine einzelne Strasse:

```powershell
python .\download_a1_motorways.py `
    --motorway A45 `
    --radius 29990 `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --output .\data\a45_motorways.json
```

## 2. Staedte bereitstellen

Die SVG-Stadtmarkierungen werden aus folgender Datei gelesen:

```text
input\MapCities.cpp
```

Die erwartete Struktur ist:

```cpp
struct MapCity {
    const char* label;
    float lat;
    float lon;
};
```

Die Stadtdatei kann vor dem Reduzierungslauf angepasst werden.

## 3. Strassen reduzieren

Dieser Schritt erzeugt einen einzigen 30-km-Strassenheader und die SVG-
Darstellungen fuer alle Bereiche.

```powershell
python .\reduce_motorways_for_display.py `
    --input-dir .\data `
    --output-dir .\display_output `
    --cities-file .\input\MapCities.cpp `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --refinement-factor 1.0 `
    --max-heading-change-deg 75 `
    --min-segment-length-m 375 `
    --carriageway-selection auto
```

Erzeugt werden unter anderem:

```text
display_output\motorway_map_30km.h
display_output\motorway_map_30km.svg
display_output\motorway_map_25km.svg
display_output\motorway_map_20km.svg
display_output\motorway_map_15km.svg
display_output\motorway_map_10km.svg
display_output\motorway_map_5km.svg
display_output\motorway_map_overview.svg
```

Der Header enthaelt:

- `MapPoint` und `MapRoad` ueber `MapTypes.h`
- ein reduziertes `kRoadAxx[]` oder `kRoadBxx[]` je Strasse
- `kMapRoads[]`
- `kMapRoadCount`

Autobahnen erhalten `MapRoadKind::kMotorway`. Bundesstrassen erhalten
`MapRoadKind::kPrimary`.

### Detailgrad

Mehr Details behalten:

```powershell
--refinement-factor 2.0
```

Staerker reduzieren:

```powershell
--refinement-factor 0.5
```

Die Fahrtrichtungsauswahl kann bei Bedarf geaendert werden:

```powershell
--carriageway-selection auto
--carriageway-selection north
--carriageway-selection east
```

`auto` ist der empfohlene Wert. `--max-heading-change-deg` begrenzt den
Richtungswechsel beim Verbinden von OSM-Teilstuecken. Mit
`--min-segment-length-m` werden kurze Rest- und Nebenabschnitte entfernt.

## 4. Wasser laden

Die Liste der Gewaesser kann automatisch aus Mittelpunkt und Radius erzeugt
werden. Das Discovery-Skript laedt dabei nur Namen und keine Geometrien:

```powershell
python .\discover_water_names.py `
    --radius 29990 `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --output .\input\WaterNames.txt
```

Danach `input\WaterNames.txt` manuell pruefen und ungewollte Gewaesserzeilen
entfernen. Standardmaessig wird die bearbeitete Auswahl aus folgender Datei
geladen:

```text
input\WaterNames.txt
```

Die Datei enthaelt einen Gewaessernamen je Zeile. Leerzeilen und Zeilen mit `#`
werden ignoriert.

```powershell
python .\download_water_features.py `
    --radius 29990 `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --water-list .\input\WaterNames.txt `
    --output .\data\water_features.json
```

Eigene Gewaesser koennen mehrfach angegeben werden:

```powershell
python .\download_water_features.py `
    --water-name Ruhr `
    --water-name Phoenix-See `
    --water-name Kemnader See `
    --water-name Harkort-See `
    --output .\data\water_features.json
```

Der Namensvergleich ignoriert Gross-/Kleinschreibung und behandelt Leerzeichen
und Bindestriche flexibel. `Phoenix-See`, `Phoenix See` und `Phoenixsee` werden
damit gleich behandelt.

Die alte Vollabfrage aller Wasserobjekte ist weiterhin moeglich:

```powershell
python .\download_water_features.py --all-water
```

Einzelne Namen koennen die Datei ersetzen:

```powershell
python .\download_water_features.py `
    --water-name Ruhr `
    --water-name Phoenix-See `
    --output .\data\water_features.json
```

## 5. Wasser reduzieren

```powershell
python .\reduce_water_for_display.py `
    --input .\data\water_features.json `
    --output-dir .\display_output `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --min-area-px 5 `
    --min-waterway-length-m 10 `
    --simplification-pixels 0.1
```

Erzeugt werden:

```text
display_output\water_map_30km.h
display_output\water_map_30km.svg
display_output\water_map_25km.svg
display_output\water_map_20km.svg
display_output\water_map_15km.svg
display_output\water_map_10km.svg
display_output\water_map_5km.svg
```

Der Header enthaelt `MapWater`, `kMapWaters[]` und `kMapWaterCount`.

Wasserfilter:

```text
--min-area-px              Mindestflaeche fuer Seen und Wasserflaechen
--min-waterway-length-m    Mindestlaenge fuer Fluesse und Kanaele
--simplification-pixels   Geometrie-Vereinfachung im Pixelraum
```

Wenn die Darstellung zu grob ist, `--simplification-pixels` reduzieren. Wenn
zu viele kleine Wasserflaechen erscheinen, `--min-area-px` erhoehen. Wenn
wichtige kurze Wasserlaeufe fehlen, `--min-waterway-length-m` reduzieren.

## 6. Kombinierte SVGs

Nach der Erzeugung von Strassen- und Wasser-SVGs werden beide Quellen je
Zoomstufe kombiniert:

```powershell
python .\combine_map_visualizations.py `
    --input-dir .\display_output
```

Erzeugt werden:

```text
display_output\map_combined_30km.svg
display_output\map_combined_25km.svg
display_output\map_combined_20km.svg
display_output\map_combined_15km.svg
display_output\map_combined_10km.svg
display_output\map_combined_5km.svg
display_output\map_combined_overview.svg
```

Die kombinierte Uebersicht enthaelt alle sechs Bereiche in einem 3x2-Raster.
Die Einzel-SVGs muessen im gleichen Ordner wie die Uebersicht bleiben.

## 7. Einbindung in das ESP32-Projekt

Folgende Dateien werden benoetigt:

```text
MapTypes.h
motorway_map_30km.h
water_map_30km.h
```

Einbindung im Zielprojekt:

```cpp
#include "MapTypes.h"
#include "motorway_map_30km.h"
#include "water_map_30km.h"
```

`MapTypes.h` wird von beiden generierten Headern verwendet und darf nicht
doppelt im Zielprojekt definiert werden.

## 8. Neuer Lauf

Fuer einen vollstaendigen neuen Lauf:

```powershell
Remove-Item .\data\*.json -Force
Remove-Item .\display_output\*.h -Force
Remove-Item .\display_output\*.svg -Force
```

Danach die Schritte 1 bis 6 erneut ausfuehren.

Die Ausgabedateien sind generiert und muessen normalerweise nicht committed
werden. Die Rohdaten sind ebenfalls regenerierbar und sollten nur bei Bedarf
im Repository abgelegt werden.
