#!/usr/bin/env python3
"""Laedt Autobahnabschnitte der A1 aus OpenStreetMap ueber Overpass herunter."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
FALLBACK_ENDPOINT = "https://overpass.kumi.systems/api/interpreter"
OVERPASS_TIMEOUT = 180
HTTP_TIMEOUT = 300
DEFAULT_RETRIES = 10
DEFAULT_RADIUS = 52000
DEFAULT_LATITUDE = 51.48415698
DEFAULT_LONGITUDE = 7.41573987


def motorway_ref_pattern(motorway: str) -> tuple[str, str]:
    """Normalisiert eine Autobahnbezeichnung und erstellt ein robustes ref-Muster."""
    match = re.fullmatch(r"([A-Za-z])\s*(\d+)", motorway.strip())
    if not match:
        raise ValueError(
            "Die Autobahn muss aus einem Buchstaben und einer Nummer bestehen, "
            "zum Beispiel A1 oder A 1."
        )

    prefix, number = match.groups()
    normalized_name = f"{prefix.upper()}{number}"
    # Erlaubt A1, A 1 und mehrere Semikolon-getrennte ref-Werte.
    pattern = rf"(^|; *){re.escape(prefix.upper())} *{number}( *;|$)"
    return normalized_name, pattern


def build_query(
    motorway: str | None,
    radius: int,
    latitude: float,
    longitude: float,
    include_trunk: bool = False,
    include_federal_roads: bool = False,
) -> str:
    """Erstellt die Overpass-Abfrage mit dem angegebenen Suchbereich."""
    ref_filter = ""
    motorway_comment = "Alle Autobahnen"
    if include_federal_roads:
        highway_filter = '["highway"~"^(motorway|trunk|primary)$"]'
        motorway_comment = "Autobahnen, A-Korridore und Bundesstrassen"
    elif include_trunk:
        highway_filter = '["highway"~"^(motorway|trunk)$"]'
        motorway_comment = "Autobahnen und A-Korridore"
    else:
        highway_filter = '["highway"="motorway"]'
    if motorway:
        normalized_name, ref_pattern = motorway_ref_pattern(motorway)
        motorway_comment = normalized_name
        ref_filter = f'\n  ["ref"~"{ref_pattern}",i]'

    return f"""[out:json][timeout:{OVERPASS_TIMEOUT}];
// {motorway_comment} im angegebenen Radius um den Radar-Mittelpunkt.
way
  {highway_filter}
{ref_filter}
  (around:{radius}, {latitude}, {longitude});

out geom qt;"""


def build_discovery_query(
    radius: int,
    latitude: float,
    longitude: float,
    include_trunk: bool = False,
    include_federal_roads: bool = False,
) -> str:
    """Erstellt eine kleine Abfrage, die nur Autobahn-Tags ohne Geometrie liefert."""
    if include_federal_roads:
        highway_filter = '["highway"~"^(motorway|trunk|primary)$"]'
    elif include_trunk:
        highway_filter = '["highway"~"^(motorway|trunk)$"]'
    else:
        highway_filter = '["highway"="motorway"]'
    return f"""[out:json][timeout:{OVERPASS_TIMEOUT}];
way
  {highway_filter}
  (around:{radius}, {latitude}, {longitude});

out tags qt;"""


def discover_motorways(
    endpoint: str,
    radius: int,
    latitude: float,
    longitude: float,
    include_trunk: bool = False,
    include_federal_roads: bool = False,
) -> list[str]:
    """Ermittelt die eindeutigen Autobahn-Referenzen im Suchgebiet."""
    discovery_query = build_discovery_query(
        radius,
        latitude,
        longitude,
        include_trunk,
        include_federal_roads,
    )
    data = json.loads(download_result(endpoint, discovery_query))
    motorways: set[str] = set()
    for element in data.get("elements", []):
        ref = element.get("tags", {}).get("ref", "")
        motorways.update(road_names_from_ref(ref))
    return sorted(motorways)


def build_turbo_url(query: str) -> str:
    """Erstellt eine URL, die die Abfrage in Overpass Turbo oeffnet."""
    encoded_query = urllib.parse.quote(query, safe="")
    return f"https://overpass-turbo.eu/?Q={encoded_query}"


def download_result(
    endpoint: str, query: str, retries: int = DEFAULT_RETRIES
) -> bytes:
    """Fuehrt die Overpass-Abfrage aus und gibt die JSON-Antwort zurueck."""
    endpoints = [endpoint]
    if endpoint != FALLBACK_ENDPOINT:
        endpoints.append(FALLBACK_ENDPOINT)

    last_error: Exception | None = None
    for endpoint_index, current_endpoint in enumerate(endpoints):
        request = urllib.request.Request(
            current_endpoint,
            data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": "get-roads-for-plane-radar/1.0",
            },
            method="POST",
        )

        for attempt in range(1, retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                    result = response.read()
                    if not result:
                        raise RuntimeError("Overpass hat eine leere Antwort geliefert.")
                    json.loads(result)
                    return result
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace").strip()
                temporary = exc.code in {429, 500, 502, 503, 504}
                last_error = RuntimeError(
                    f"Overpass-Serverfehler HTTP {exc.code}"
                    f"{': ' + error_body[:500] if error_body else ''}"
                )
                if not temporary:
                    raise last_error from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = RuntimeError(f"Overpass-Abfrage fehlgeschlagen: {exc}")

            if attempt < retries:
                wait_seconds = min(60, 2**attempt)
                print(
                    f"Temporaerer Fehler bei {current_endpoint}, neuer Versuch "
                    f"in {wait_seconds} s ({attempt}/{retries}) ...",
                    file=sys.stderr,
                )
                time.sleep(wait_seconds)

        if endpoint_index < len(endpoints) - 1:
            print(
                f"Server nicht erreichbar: {current_endpoint}. "
                f"Wechsel zu {endpoints[endpoint_index + 1]} ...",
                file=sys.stderr,
            )

    raise last_error or RuntimeError("Overpass-Abfrage fehlgeschlagen.")


def write_atomically(path: Path, content: bytes) -> None:
    """Schreibt die Datei zuerst temporaer, damit kein unvollstaendiges JSON bleibt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        temporary_path.write_bytes(content)
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def road_names_from_ref(ref: str) -> set[str]:
    """Liest A- und B-Referenzen aus einem OSM-ref-Tag wie A1;B54 aus."""
    return {
        f"{prefix.upper()}{number}"
        for prefix, number in re.findall(
            r"(?:^|;)\s*([AB])\s*(\d+)(?=\s*(?:;|$))", ref, re.I
        )
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fuehrt die Autobahn-Overpass-Abfrage aus und speichert das Ergebnis als JSON."
    )
    parser.add_argument(
        "--motorway",
        help=(
            "Optional: Autobahnbezeichnung, zum Beispiel A1 oder A 1. "
            "Ohne Angabe werden alle Autobahnen abgefragt."
        ),
    )
    parser.add_argument(
        "--include-trunk",
        action="store_true",
        help="Auch trunk-A-Korridorabschnitte neben motorway beruecksichtigen.",
    )
    parser.add_argument(
        "--include-federal-roads",
        action="store_true",
        help=(
            "Auch Bundesstrassen mit B-Referenz ueber motorway, trunk und "
            "primary beruecksichtigen."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Zieldatei fuer eine einzelne Autobahn (Standard: <autobahn>_motorways.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Zielordner fuer die getrennten Autobahn-Dateien",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"Overpass-Endpunkt (Standard: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=DEFAULT_RADIUS,
        help=f"Suchradius in Metern (Standard: {DEFAULT_RADIUS})",
    )
    parser.add_argument(
        "--latitude",
        type=float,
        default=DEFAULT_LATITUDE,
        help=f"Ursprungs-Breitengrad (Standard: {DEFAULT_LATITUDE})",
    )
    parser.add_argument(
        "--longitude",
        type=float,
        default=DEFAULT_LONGITUDE,
        help=f"Ursprungs-Laengengrad (Standard: {DEFAULT_LONGITUDE})",
    )
    parser.add_argument(
        "--no-url",
        action="store_true",
        help="Die Overpass-Turbo-URL nicht ausgeben.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        search_description = (
            args.motorway if args.motorway else "alle Autobahnen"
        )
        print("Overpass-Autobahnsuche gestartet.")
        print(f"  Ziel: {search_description}")
        print(f"  Radius: {args.radius} m")
        print(f"  Ursprung: {args.latitude}, {args.longitude}")
        print(f"  Overpass-Endpunkt: {args.endpoint}")
        print(f"  Trunk-A-Korridore: {'ja' if args.include_trunk else 'nein'}")
        print(
            f"  Bundesstrassen: {'ja' if args.include_federal_roads else 'nein'}"
        )

        if args.radius <= 0:
            raise ValueError("Der Radius muss groesser als 0 sein.")
        if not -90 <= args.latitude <= 90:
            raise ValueError("Der Breitengrad muss zwischen -90 und 90 liegen.")
        if not -180 <= args.longitude <= 180:
            raise ValueError("Der Laengengrad muss zwischen -180 und 180 liegen.")

        if args.motorway and args.output_dir:
            raise ValueError("--output und --output-dir koennen nicht kombiniert werden.")
        if args.motorway:
            normalized_name, _ = motorway_ref_pattern(args.motorway)
            query = build_query(
                args.motorway,
                args.radius,
                args.latitude,
                args.longitude,
                args.include_trunk,
                args.include_federal_roads,
            )
            output = args.output or Path(f"{normalized_name.lower()}_motorways.json")
            print(f"\n[1/1] Frage {normalized_name} bei Overpass ab ...")
            result = download_result(args.endpoint, query)
            print(f"[1/1] Antwort empfangen, speichere {output} ...")
            write_atomically(output, result)
            written_files = [output]
        elif args.output:
            raise ValueError("Im automatischen Modus bitte --output-dir verwenden.")
        else:
            discovery_query = build_discovery_query(
                args.radius,
                args.latitude,
                args.longitude,
                args.include_trunk,
                args.include_federal_roads,
            )
            print("\n[1/2] Suche Autobahn-Referenzen ohne Geometrien ...")
            motorways = discover_motorways(
                args.endpoint,
                args.radius,
                args.latitude,
                args.longitude,
                args.include_trunk,
                args.include_federal_roads,
            )
            if not motorways:
                raise RuntimeError(
                    "Im Suchgebiet wurden keine Autobahnen mit auswertbarem ref-Tag gefunden."
                )

            print(
                f"[1/2] {len(motorways)} Autobahnen gefunden: "
                f"{', '.join(motorways)}"
            )
            output_dir = args.output_dir or Path(".")
            written_files = []
            total = len(motorways)
            for index, motorway in enumerate(motorways, start=1):
                progress = index / total * 100
                print(
                    f"[2/2] [{index}/{total} | {progress:5.1f}%] "
                    f"Frage {motorway} ab ..."
                )
                query = build_query(
                    motorway,
                    args.radius,
                    args.latitude,
                    args.longitude,
                    args.include_trunk,
                    args.include_federal_roads,
                )
                result = download_result(args.endpoint, query)
                output_path = output_dir / f"{motorway.lower()}_motorways.json"
                print(
                    f"[2/2] [{index}/{total} | {progress:5.1f}%] "
                    f"Speichere {output_path} ..."
                )
                write_atomically(output_path, result)
                written_files.append(output_path)
                print(
                    f"[2/2] [{index}/{total} | {progress:5.1f}%] "
                    f"{motorway} abgeschlossen."
                )
            query = discovery_query
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    for output_path in written_files:
        print(f"Ergebnis gespeichert: {output_path.resolve()}")
    print(f"Fertig: {len(written_files)} Datei(en) erfolgreich gespeichert.")
    if not args.no_url:
        print(f"Abfrage in Overpass Turbo: {build_turbo_url(query)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
