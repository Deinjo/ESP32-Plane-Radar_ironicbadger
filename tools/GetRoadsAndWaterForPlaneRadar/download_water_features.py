#!/usr/bin/env python3
"""Laedt Seen, Fluesse und Kanaele aus OpenStreetMap ueber Overpass."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from download_a1_motorways import (
    DEFAULT_ENDPOINT,
    DEFAULT_LATITUDE,
    DEFAULT_RADIUS,
    DEFAULT_LONGITUDE,
    OVERPASS_TIMEOUT,
    download_result,
)


DEFAULT_WATER_LIST = Path("input/WaterNames.txt")


def flexible_name_pattern(name: str) -> str:
    """Erlaubt optionale Leerzeichen oder Bindestriche zwischen Namensteilen."""
    parts = re.findall(r"[\wÄÖÜäöüß]+", name, re.UNICODE)
    if not parts:
        raise ValueError(f"Ungueltiger Gewaessername: {name}")
    return r"[- ]*".join(re.escape(part) for part in parts)


def load_water_names(path: Path) -> tuple[str, ...]:
    """Liest Gewaessernamen aus einer Textdatei, eine Zeile je Name."""
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if name and not name.startswith("#"):
            names.append(name)
    if not names:
        raise ValueError(f"Keine Gewaessernamen in {path} gefunden.")
    return tuple(names)


def build_query(
    radius: int,
    latitude: float,
    longitude: float,
    water_names: tuple[str, ...] | None = None,
) -> str:
    name_filter = ""
    if water_names:
        pattern = "|".join(
            flexible_name_pattern(name) for name in water_names
        )
        name_filter = f'\n  ["name"~"^({pattern})$",i]'
    return f"""[out:json][timeout:{OVERPASS_TIMEOUT}];
(
  way["natural"="water"]{name_filter}(around:{radius}, {latitude}, {longitude});
  relation["natural"="water"]{name_filter}(around:{radius}, {latitude}, {longitude});
  way["waterway"~"^(river|canal|dock)$"]{name_filter}(around:{radius}, {latitude}, {longitude});
  way["landuse"="basin"]{name_filter}(around:{radius}, {latitude}, {longitude});
  relation["landuse"="basin"]{name_filter}(around:{radius}, {latitude}, {longitude});
);
out geom qt;"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Laedt Wasserflaechen und groessere Wasserlaeufe als Overpass-JSON."
    )
    parser.add_argument("--radius", type=int, default=DEFAULT_RADIUS)
    parser.add_argument("--latitude", type=float, default=DEFAULT_LATITUDE)
    parser.add_argument("--longitude", type=float, default=DEFAULT_LONGITUDE)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument(
        "--water-name",
        action="append",
        dest="water_names",
        help="Gewaessername; kann mehrfach angegeben werden.",
    )
    parser.add_argument(
        "--water-list",
        type=Path,
        default=DEFAULT_WATER_LIST,
        help="Datei mit einem Gewaessernamen je Zeile.",
    )
    parser.add_argument(
        "--all-water",
        action="store_true",
        help="Alle Wasserflaechen und Wasserlaeufe wie in der alten Abfrage laden.",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("water_features.json")
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.radius <= 0:
            raise ValueError("Der Radius muss groesser als 0 sein.")
        if not -90 <= args.latitude <= 90:
            raise ValueError("Der Breitengrad muss zwischen -90 und 90 liegen.")
        if not -180 <= args.longitude <= 180:
            raise ValueError("Der Laengengrad muss zwischen -180 und 180 liegen.")

        if args.all_water:
            water_names = None
        elif args.water_names:
            water_names = tuple(args.water_names)
        else:
            water_names = load_water_names(args.water_list)
            print(f"{len(water_names)} Gewaesser aus {args.water_list} geladen.")
        query = build_query(
            args.radius, args.latitude, args.longitude, water_names
        )
        print("Lade Wasserflaechen, Fluesse und Kanaele ...")
        result = download_result(args.endpoint, query)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(result)
        print(f"Wasserdatei gespeichert: {args.output.resolve()}")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Fehler: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
