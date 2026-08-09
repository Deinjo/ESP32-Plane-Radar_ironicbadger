#!/usr/bin/env python3
"""Reduziert Wasser-Overpass-Daten fuer MapWater und eine SVG-Vorschau."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from reduce_motorways_for_display import (
    DISPLAY_SIZE,
    DISPLAY_RANGES_KM,
    EARTH_RADIUS_M,
    DEFAULT_LATITUDE,
    DEFAULT_LONGITUDE,
    pixels_to_coordinates,
    point_inside,
    project_to_pixels,
    simplify_line,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("water_features.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--latitude", type=float, default=DEFAULT_LATITUDE)
    parser.add_argument("--longitude", type=float, default=DEFAULT_LONGITUDE)
    parser.add_argument("--refinement-factor", type=float, default=1.0)
    parser.add_argument(
        "--min-area-px",
        type=float,
        default=5.0,
        help="Mindestflaeche einer Wasserflaeche in Display-Pixeln (Standard: 5)",
    )
    parser.add_argument(
        "--min-waterway-length-m",
        type=float,
        default=1000.0,
        help="Mindestlaenge von Fluss/Kanal in Metern (Standard: 1000)",
    )
    parser.add_argument(
        "--simplification-pixels",
        type=float,
        default=2.0,
        help="Vereinfachungstoleranz in Display-Pixeln (Standard: 2)",
    )
    return parser.parse_args()


def load_features(path: Path) -> list[tuple[str, str, list[tuple[float, float]]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    features = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        kind = "area" if tags.get("natural") == "water" else None
        if tags.get("waterway") == "river":
            kind = "river"
        elif tags.get("waterway") == "canal":
            kind = "canal"
        if kind is None:
            continue
        geometry = element.get("geometry", [])
        coordinates = [
            (float(point["lat"]), float(point["lon"]))
            for point in geometry
            if "lat" in point and "lon" in point
        ]
        if len(coordinates) >= 2:
            features.append((f"{element.get('type', 'way')}_{element.get('id', len(features))}", kind, coordinates))
        for member in element.get("members", []):
            member_geometry = member.get("geometry", [])
            member_coordinates = [
                (float(point["lat"]), float(point["lon"]))
                for point in member_geometry
                if "lat" in point and "lon" in point
            ]
            if kind == "area" and len(member_coordinates) >= 2:
                features.append((f"relation_{element.get('id', len(features))}_{len(features)}", kind, member_coordinates))
    return features


def process_features(
    features: list[tuple[str, str, list[tuple[float, float]]]],
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    range_m = 30_000.0
    tolerance = max(0.25, args.simplification_pixels / args.refinement_factor)
    result = []
    for identifier, kind, coordinates in features:
        pixels = [
            project_to_pixels(lat, lon, args.latitude, args.longitude, range_m)
            for lat, lon in coordinates
        ]
        if kind == "area":
            area = abs(
                sum(
                    pixels[index][0] * pixels[(index + 1) % len(pixels)][1]
                    - pixels[(index + 1) % len(pixels)][0] * pixels[index][1]
                    for index in range(len(pixels))
                )
                / 2
            )
            bounding_area = (
                max(point[0] for point in pixels) - min(point[0] for point in pixels)
            ) * (
                max(point[1] for point in pixels) - min(point[1] for point in pixels)
            )
            # Relation members are often open outer-ring fragments.
            area = max(area, bounding_area)
            if area < args.min_area_px:
                continue
        else:
            length_pixels = sum(
                ((pixels[index][0] - pixels[index - 1][0]) ** 2
                 + (pixels[index][1] - pixels[index - 1][1]) ** 2) ** 0.5
                for index in range(1, len(pixels))
            )
            minimum_length_pixels = args.min_waterway_length_m * DISPLAY_SIZE / 60_000
            if length_pixels < minimum_length_pixels:
                continue
        visible = [point for point in pixels if point_inside(point)]
        if len(visible) < 2:
            continue
        reduced = simplify_line(visible, tolerance)
        if len(reduced) < 2:
            continue
        result.append(
            {
                "id": identifier,
                "kind": kind,
                "coordinates": [
                    list(
                        pixels_to_coordinates(
                            x, y, args.latitude, args.longitude, range_m
                        )
                    )
                    for x, y in reduced
                ],
            }
        )
    return result


def write_header(path: Path, features: list[dict[str, object]]) -> None:
    lines = [
        "#pragma once",
        "",
        '#include "MapTypes.h"',
        "",
        "// Generated by reduce_water_for_display.py",
        "// Map data (c) OpenStreetMap contributors, ODbL.",
        "",
    ]
    entries = []
    for index, feature in enumerate(features):
        identifier = re.sub(r"[^A-Za-z0-9_]", "_", str(feature["id"]))
        array_name = f"kWater_{identifier}_{index}"
        lines.append(f"constexpr MapPoint {array_name}[] = {{")
        for lat, lon in feature["coordinates"]:
            lines.append(f"    {{{lat:.6f}f, {lon:.6f}f}},")
        lines.extend(["};", ""])
        kind = {"area": "kArea", "river": "kRiver", "canal": "kCanal"}[feature["kind"]]
        entries.append((str(feature["id"]), array_name, kind))
    lines.append("constexpr MapWater kMapWaters[] = {")
    for identifier, array_name, kind in entries:
        lines.extend(
            [
                f'    {{"{identifier}", {array_name}, sizeof({array_name}) / sizeof({array_name}[0]),',
                f"    MapWaterKind::{kind}}},",
            ]
        )
    lines.extend(["};", "", "constexpr size_t kMapWaterCount =", "    sizeof(kMapWaters) / sizeof(kMapWaters[0]);", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_svg(
    path: Path,
    args: argparse.Namespace,
    features: list[dict[str, object]],
    range_km: int,
) -> None:
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240">',
        '<rect width="240" height="240" fill="none" />',
        '<defs><clipPath id="water-map-area"><circle cx="120" cy="120" r="119" /></clipPath></defs>',
        '<g clip-path="url(#water-map-area)">',
    ]
    for feature in features:
        points = []
        for lat, lon in feature["coordinates"]:
            x, y = project_to_pixels(
                lat, lon, args.latitude, args.longitude, range_km * 1000
            )
            points.append(f"{x:.1f},{y:.1f}")
        if len(points) < 2:
            continue
        if feature["kind"] == "area":
            lines.append(f'<polygon points="{" ".join(points)}" fill="#d7edf5" stroke="#77acc2" stroke-width="0.7" />')
        else:
            lines.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="#77acc2" stroke-width="1" />')
    lines.extend(
        [
            "</g>",
            '<circle cx="120" cy="120" r="119" fill="none" stroke="black" stroke-width="1.5" />',
            "</svg>",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        if args.refinement_factor <= 0:
            raise ValueError("Der Verfeinerungsfaktor muss groesser als 0 sein.")
        if args.min_area_px <= 0 or args.min_waterway_length_m <= 0:
            raise ValueError("Die Wasserfilterwerte muessen groesser als 0 sein.")
        if args.simplification_pixels <= 0:
            raise ValueError("Die Vereinfachungstoleranz muss groesser als 0 sein.")
        features = process_features(load_features(args.input), args)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_header(args.output_dir / "water_map_30km.h", features)
        for range_km in DISPLAY_RANGES_KM:
            write_svg(
                args.output_dir / f"water_map_{range_km}km.svg",
                args,
                features,
                range_km,
            )
        print(f"{len(features)} Wassergeometrien gespeichert.")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Fehler: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
