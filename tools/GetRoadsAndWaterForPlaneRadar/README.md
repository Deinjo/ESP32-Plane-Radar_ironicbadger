# GetRoadsForPlaneRadar

Laedt Autobahnabschnitte aus OpenStreetMap ueber die Overpass API herunter.

## Voraussetzungen

- Python 3.9 oder neuer
- Internetzugang

Es werden keine externen Python-Pakete benoetigt. Das Skript verwendet nur die
Python-Standardbibliothek.

Die Overpass-Abfrage verwendet ein Server-Timeout von 180 Sekunden und laedt
die Geometrien sortiert aus. Bevorzugt wird `overpass-api.de`. Bei temporaeren
Serverfehlern oder einem Timeout wechselt das Skript automatisch zu
`overpass.kumi.systems`. Bei sehr grossen Suchradien kann die Abfrage je nach
Serverauslastung trotzdem mehrere Minuten dauern. Pro Server werden bis zu zehn
Versuche ausgefuehrt; zwischen den Versuchen wird maximal 60 Sekunden gewartet.

## Ausfuehrung

PowerShell im Projektordner oeffnen und ausfuehren:

```powershell
python .\download_a1_motorways.py --motorway A1
```

Das Ergebnis wird als `a1_motorways.json` im aktuellen Ordner gespeichert.
Die Datei enthaelt die Geometrie der gefundenen Wege im Overpass-JSON-Format.

## Alle Autobahnen im Suchgebiet

Wird `--motorway` weggelassen, fragt das Skript automatisch alle Wege mit
`highway=motorway` innerhalb des angegebenen Radius ab:

```powershell
python .\download_a1_motorways.py `
    --radius 52000 `
    --latitude 51.48415698 `
    --longitude 7.41573987
```

Zuerst werden ohne Geometrien nur die vorhandenen Autobahn-Referenzen ermittelt.
Danach wird je erkannter Autobahn eine eigene Geometrie-Abfrage ausgefuehrt und
eine Datei erzeugt, zum Beispiel:

```text
a1_motorways.json
a2_motorways.json
a45_motorways.json
```

Mit `--output-dir` kann ein Zielordner fuer diese Dateien angegeben werden:

```powershell
python .\download_a1_motorways.py `
    --radius 52000 `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --output-dir .\data
```

Wenn auch als `trunk` klassifizierte A-Korridorabschnitte, zum Beispiel Teile
der A52 bei Essen, beruecksichtigt werden sollen:

```powershell
python .\download_a1_motorways.py `
    --radius 52000 `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --include-trunk `
    --output-dir .\data
```

Ohne `--include-trunk` werden ausschliesslich `highway=motorway`-Ways geladen.
Mit dem Parameter werden zusaetzlich `highway=trunk`-Ways mit einer A-Referenz
geladen. `motorway_link` und `primary` bleiben ausgeschlossen.

Bundesstrassen koennen zusaetzlich mit `--include-federal-roads` geladen werden:

```powershell
python .\download_a1_motorways.py `
    --radius 52000 `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --include-federal-roads `
    --output-dir .\data
```

Dann werden A- und B-Referenzen erkannt. Fuer B-Referenzen werden `trunk`- und
`primary`-Ways mitgeladen und im Ausgabeheader als `MapRoadKind::kPrimary`
eingetragen. A-Referenzen bleiben `MapRoadKind::kMotorway`.

Die Erkennung basiert auf den OSM-Tags `highway=motorway` und `ref`. Anschluss-
stellen, Bundesstrassen und andere Strassentypen werden dadurch nicht als
Autobahnen aufgenommen. Wege mit mehreren Referenzen werden in die jeweils
passenden Autobahn-Dateien geschrieben.

## Konsolenausgabe

Waehrend der Ausfuehrung zeigt das Skript den aktuellen Schritt, die Anzahl der
gefundenen Autobahnen und den Fortschritt je Einzelabfrage an. Bei temporaren
Overpass-Fehlern werden zusaetzlich die automatischen Wiederholungsversuche
angezeigt.

## Display-Daten erzeugen

Das zweite Skript `reduce_motorways_for_display.py` verarbeitet die erzeugten
Autobahn-Dateien zu einem C++-Header mit echten Breitengrad-/Laengengrad-
Koordinaten. Die Linien sind fuer das Zeichnen auf einem runden 240x240-Display
geeignet. Die Reduzierung orientiert sich an der Displayaufloesung, die Ausgabe
bleibt aber in geografischen Koordinaten.

Es wird genau ein Strassen-Header fuer den 30-km-Bereich erzeugt. Zusaetzlich
werden SVG-Visualisierungen fuer sechs Display-Bereiche erzeugt: `30`, `25`,
`20`, `15`, `10` und `5 km`. Die
SVG enthaelt:

- den Ursprung als roten Punkt in der Mitte
- den schwarzen Aussenrand des gewaehlten Bereichs
- gruene, gestrichelte Radiusringe im Abstand von 5 km
- gruene Koordinatenachsen von Rand zu Rand
- die reduzierten Autobahnlinien in unterschiedlichen Farben
- die Staedte aus `input\MapCities.cpp` als hellgraue Punkte mit Labels

Die Autobahnlinien der SVG werden nach der Header-Erzeugung wieder aus genau
dieser `.h`-Datei gelesen. Dadurch zeigt die Vorschau exakt die Daten, die in
das C++-Projekt integriert werden. Die Linien sind 1 px breit und haben die
Farbe `rgb(105, 115, 125)` beziehungsweise `#69737d`.
Bundesstrassen werden in dunklem Orange `#b85c00` dargestellt.

Zusaetzlich wird eine zweite SVG mit den unveraenderten Overpass-Geometrien
geschrieben. Beide SVG-Dateien verwenden eine Autobahnlinienbreite von 1 px:

```text
motorway_map_30km.svg       reduzierte Daten aus dem generierten Header
motorway_map_30km_raw.svg   unveraenderte Overpass-Rohdaten
```

Beispiel fuer den Bereich von 30 km um den Radar-Mittelpunkt:

```powershell
python .\reduce_motorways_for_display.py `
    --input-dir .\data `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --range-km 30 `
    --cities-file .\input\MapCities.cpp `
    --output .\data\motorway_map_30km.h `
    --svg-output .\data\motorway_map_30km.svg `
    --raw-svg-output .\data\motorway_map_30km_raw.svg
```

Die sechs Bereiche werden bei jedem Lauf erzeugt:

```powershell
python .\reduce_motorways_for_display.py `
    --input-dir .\data `
    --output-dir .\display_output `
    --latitude 51.48415698 `
    --longitude 7.41573987
```

Dabei entstehen `motorway_map_30km.h` sowie die SVG-Dateien
`motorway_map_30km.svg`, `motorway_map_25km.svg`, `motorway_map_20km.svg`,
`motorway_map_15km.svg`, `motorway_map_10km.svg` und
`motorway_map_5km.svg`, jeweils mit passender Rohdaten-SVG. Alle reduzierten
SVGs verwenden denselben 30-km-Header und zeigen daraus nur den jeweils
kleineren Ausschnitt.

Zusaetzlich wird eine Gesamtuebersicht als `motorway_map_overview.svg` erzeugt.
Sie enthaelt alle sechs reduzierten Einzel-SVGs in einem 3x2-Raster. Die
Uebersicht muss im selben Ordner wie die Einzel-SVGs bleiben, da sie diese ueber
relative Dateiverweise einbindet.

`--range-km` waehlt den Bereich aus, fuer den benutzerdefinierte SVG-Dateinamen
mit `--svg-output` und `--raw-svg-output` gelten. Der Header bleibt immer der
30-km-Header. Normalerweise werden keine einzelnen Dateinamen benoetigt.
`--output` bleibt als optionale Ueberschreibung fuer den Header erhalten.

Der Detailgrad kann mit `--refinement-factor` manuell angepasst werden:

```powershell
# Standard: ausgewogene Reduzierung
python .\reduce_motorways_for_display.py --input-dir .\data --range-km 30 --refinement-factor 1.0

# Mehr Geometriedetails behalten
python .\reduce_motorways_for_display.py --input-dir .\data --range-km 30 --refinement-factor 2.0

# Staerker reduzieren
python .\reduce_motorways_for_display.py --input-dir .\data --range-km 30 --refinement-factor 0.5
```

Ein Faktor groesser als `1.0` behaelt mehr Punkte und trennt nahe Linien eher;
ein Faktor kleiner als `1.0` reduziert staerker. Der Filter gegen einzelne
punktartige Restsegmente bleibt unabhaengig vom Faktor aktiv.

Die Centerline-Erzeugung kann zusaetzlich gesteuert werden:

```powershell
python .\reduce_motorways_for_display.py `
    --input-dir .\data `
    --output-dir .\display_output `
    --max-heading-change-deg 75 `
    --min-segment-length-m 375 `
    --carriageway-selection auto
```

`--max-heading-change-deg` begrenzt den Richtungswechsel beim Verbinden von
OSM-Teilstuecken. `--min-segment-length-m` entfernt kurze Seiten- oder
Restsegmente. Beide Werte werden beim einmaligen Erzeugen des 30-km-Headers
angewendet und wirken damit identisch auf alle SVG-Zoomstufen.

Mit `--carriageway-selection` wird pro Autobahn nur ein repraesentativer
Fahrbahnverlauf verfolgt:

```powershell
--carriageway-selection auto
--carriageway-selection north
--carriageway-selection east
```

`auto` waehlt anhand der Hauptrichtung einen Start am noerdlichen oder
oestlichen Rand. Das Skript probiert inzwischen mehrere moegliche Startpunkte
und beide Laufrichtungen aus und bewertet die sichtbare zusammenhaengende
Laenge. Danach werden Teilstuecke mit moeglichst kleiner Richtungsabweichung
verfolgt. Dadurch wird pro Autobahn nur noch ein `kRoadAxx[]`-Array in den
Header geschrieben und kurze Aussen- oder Seitenast-Verlaeufe werden seltener
ausgewaehlt.

Das Skript reduziert die Geometrien pixelbezogen mit Douglas-Peucker. Dadurch
werden kleine Kurven, viele Zwischenpunkte und doppelte identische Linien
entfernt und zusammenhaengende Teilstuecke verbunden. Parallelfahrbahnen werden
nicht mehr gemittelt, sondern durch die Auswahl eines repraesentativen Verlaufs
vermieden. Sehr kurze Restsegmente unterhalb von
1,5 Pixeln werden entfernt, damit sie auf dem Display nicht als einzelne Punkte
erscheinen. Die C++-Ausgabe sieht
beispielsweise so aus:

```cpp
constexpr MapPoint kRoadA45[] = {
    {51.580900f, 7.366000f},
    {51.565400f, 7.359800f},
    {51.549100f, 7.358500f},
};
```

Pro Autobahn wird das laengste zusammenhaengende, reduzierte Liniensegment als
`kRoadA<Nummer>` ausgegeben. Weitere reduzierte Segmente derselben Autobahn
bleiben erhalten und werden als `kRoadA<Nummer>_1`, `kRoadA<Nummer>_2` usw.
ausgegeben. Dadurch gehen Teilstuecke an Autobahnkreuzen oder getrennte
Abschnitte nicht verloren. Die Datei kann direkt in das bestehende C++-Projekt
uebernommen werden. Die reduzierte SVG verwendet alle diese Arrays.
Optional kann weiterhin JSON erzeugt werden:

```powershell
python .\reduce_motorways_for_display.py `
    --input-dir .\data `
    --range-km 30 `
    --format json `
    --output .\data\motorway_map_30km.json
```

## Wasser reduzieren

Der Wasser-Downloader verwendet standardmaessig eine kuratierte Namensliste:
Ruhr, Dortmund-Ems-Kanal, Dortmunder Hafen, Kemnader See, Phoenix-See,
Harkort-See, Datteln-Hamm-Kanal und Rhein-Herne-Kanal. Dadurch werden kleine
und unbedeutende Gewaesser nicht erst heruntergeladen.

```powershell
python .\download_water_features.py `
    --radius 52000 `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --output .\data\water_features.json
```

Eigene Namen koennen mehrfach angegeben werden:

```powershell
python .\download_water_features.py `
    --water-name Ruhr `
    --water-name Phoenix-See `
    --water-name Kemnader-See `
    --output .\data\water_features.json
```

Der Namensvergleich ignoriert Gross-/Kleinschreibung und behandelt Leerzeichen
und Bindestriche flexibel. Damit werden beispielsweise `Phoenix-See`,
`Phoenix See` und `Phoenixsee` gleich behandelt. Der restliche Name muss mit
dem OSM-Tag `name` uebereinstimmen.

Die alte Vollabfrage bleibt optional verfuegbar:

```powershell
python .\download_water_features.py --all-water
```

Die Wasserverarbeitung filtert kleine Wasserflaechen und kurze Wasserlaeufe
bereits vor der Header-Erzeugung:

```powershell
python .\reduce_water_for_display.py `
    --input .\data\water_features.json `
    --output-dir .\display_output `
    --latitude 51.48415698 `
    --longitude 7.41573987 `
    --min-area-px 30 `
    --min-waterway-length-m 1000 `
    --simplification-pixels 2
```

Die Parameter bedeuten:

- `--min-area-px`: kleine Wasserflaechen unterhalb dieser Displayflaeche werden entfernt
- `--min-waterway-length-m`: kurze Fluesse und Kanaele werden entfernt
- `--simplification-pixels`: Vereinfachung der verbleibenden Geometrien

Bei weiterhin zu grosser Ausgabe koennen beispielsweise `--min-area-px 100`,
`--min-waterway-length-m 2000` und `--simplification-pixels 3` verwendet werden.

## Kombinierte SVGs

Nach der Erzeugung der Straßen- und Wasser-SVGs können beide Datenquellen je
Zoomstufe kombiniert werden:

```powershell
python .\combine_map_visualizations.py `
    --input-dir .\display_output
```

Erzeugt werden:

```text
map_combined_30km.svg
map_combined_25km.svg
map_combined_20km.svg
map_combined_15km.svg
map_combined_10km.svg
map_combined_5km.svg
map_combined_overview.svg
```

Die Übersicht enthält alle sechs kombinierten Darstellungen. Die kombinierten
SVGs erwarten die jeweiligen Straßen- und Wasser-SVGs im gleichen Ordner.

Die Autobahn kann mit oder ohne Leerzeichen angegeben werden, zum Beispiel
`A1` oder `A 1`. Die Abfrage erkennt auch Eintraege mit mehreren Referenzen,
zum Beispiel `A1;B54`.

## Suchbereich angeben

Der Radius wird in Metern angegeben. Breitengrad und Laengengrad bilden den
Mittelpunkt des Suchbereichs:

```powershell
python .\download_a1_motorways.py `
    --motorway A1 `
    --radius 52000 `
    --latitude 51.48415698 `
    --longitude 7.41573987
```

Wenn Radius und Koordinaten nicht angegeben werden, verwendet das Skript die
Werte aus der urspruenglichen Abfrage: 52.000 Meter, Breitengrad `51.48415698`
und Laengengrad `7.41573987`.

## Optionen

```powershell
# Anderen Dateinamen verwenden
python .\download_a1_motorways.py --output .\data\a1.json

# Keine Overpass-Turbo-URL ausgeben
python .\download_a1_motorways.py --no-url

# Hilfe anzeigen
python .\download_a1_motorways.py --help
```

Das Skript gibt nach erfolgreicher Ausfuehrung auch eine URL aus, mit der die
Abfrage direkt in Overpass Turbo geoeffnet werden kann.
