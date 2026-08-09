#!/usr/bin/env python3
"""Erzeugt reduzierte Autobahn-Linien fuer ein rundes 240x240-Display."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
from pathlib import Path
from typing import Iterable


DISPLAY_SIZE = 240
MIN_DISPLAY_LINE_LENGTH = 1.5
DISPLAY_RANGES_KM = (30, 25, 20, 15, 10, 5)
DEFAULT_MAX_HEADING_CHANGE_DEG = 75.0
DEFAULT_MIN_SEGMENT_LENGTH_M = 375.0
MOTORWAY_COLOR = "#69737d"
FEDERAL_ROAD_COLOR = "#b85c00"
DEFAULT_LATITUDE = 51.48415698
DEFAULT_LONGITUDE = 7.41573987
DEFAULT_RANGE_KM = 30
EARTH_RADIUS_M = 6_371_000.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reduziert Overpass-Autobahndaten fuer ein rundes 240x240-Display."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("."),
        help="Ordner mit *_motorways.json-Dateien (Standard: aktueller Ordner)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Ausgabedatei (Standard: motorway_map_<bereich>km.h)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Zielordner fuer Header und SVG-Dateien (Standard: aktueller Ordner)",
    )
    parser.add_argument(
        "--format",
        choices=("cpp", "json"),
        default="cpp",
        help="Ausgabeformat: cpp oder json (Standard: cpp)",
    )
    parser.add_argument(
        "--svg-output",
        type=Path,
        default=None,
        help="SVG-Ausgabe (Standard: motorway_map_<bereich>km.svg)",
    )
    parser.add_argument(
        "--raw-svg-output",
        type=Path,
        default=None,
        help="SVG-Ausgabe der unveraenderten Overpass-Daten",
    )
    parser.add_argument(
        "--overview-svg-output",
        type=Path,
        default=None,
        help="SVG-Uebersicht aller sechs Bereiche",
    )
    parser.add_argument(
        "--cities-file",
        type=Path,
        default=Path("input/MapCities.cpp"),
        help="C++-Datei mit MapCity-Definitionen",
    )
    parser.add_argument(
        "--latitude",
        type=float,
        default=DEFAULT_LATITUDE,
        help=f"Mittelpunkt-Breitengrad (Standard: {DEFAULT_LATITUDE})",
    )
    parser.add_argument(
        "--longitude",
        type=float,
        default=DEFAULT_LONGITUDE,
        help=f"Mittelpunkt-Laengengrad (Standard: {DEFAULT_LONGITUDE})",
    )
    parser.add_argument(
        "--range-km",
        type=int,
        choices=DISPLAY_RANGES_KM,
        default=DEFAULT_RANGE_KM,
        help=(
            "Bereich fuer benutzerdefinierte SVG-Ausgaben; der Strassen-Header "
            "wird immer fuer 30 km erzeugt (Standard: 30)"
        ),
    )
    parser.add_argument(
        "--refinement-factor",
        type=float,
        default=1.0,
        help=(
            "Detailgrad der Reduzierung: >1 mehr Details, <1 staerkere "
            "Reduzierung (Standard: 1.0)"
        ),
    )
    parser.add_argument(
        "--max-heading-change-deg",
        type=float,
        default=DEFAULT_MAX_HEADING_CHANGE_DEG,
        help=(
            "Maximaler Richtungswechsel beim Verbinden von Teilstuecken "
            f"(Standard: {DEFAULT_MAX_HEADING_CHANGE_DEG:g} Grad)"
        ),
    )
    parser.add_argument(
        "--min-segment-length-m",
        type=float,
        default=DEFAULT_MIN_SEGMENT_LENGTH_M,
        help=(
            "Mindestlaenge eines reduzierten Liniensegments in Metern "
            f"(Standard: {DEFAULT_MIN_SEGMENT_LENGTH_M:g})"
        ),
    )
    parser.add_argument(
        "--carriageway-selection",
        choices=("auto", "north", "east"),
        default="auto",
        help=(
            "Auswahl der reprasentativen Fahrtrichtung: auto, north oder east "
            "(Standard: auto)"
        ),
    )
    return parser.parse_args()


def project_to_pixels(
    latitude: float,
    longitude: float,
    center_latitude: float,
    center_longitude: float,
    range_m: float,
) -> tuple[float, float]:
    """Projiziert WGS84-Koordinaten lokal auf das 240x240-Display."""
    latitude_delta = math.radians(latitude - center_latitude)
    longitude_delta = math.radians(longitude - center_longitude)
    x_m = EARTH_RADIUS_M * longitude_delta * math.cos(math.radians(center_latitude))
    y_m = EARTH_RADIUS_M * latitude_delta
    pixels_per_meter = DISPLAY_SIZE / (2 * range_m)
    return (
        DISPLAY_SIZE / 2 + x_m * pixels_per_meter,
        DISPLAY_SIZE / 2 - y_m * pixels_per_meter,
    )


def pixels_to_coordinates(
    x: float,
    y: float,
    center_latitude: float,
    center_longitude: float,
    range_m: float,
) -> tuple[float, float]:
    """Wandelt Display-Pixel zurueck in Breitengrad und Laengengrad."""
    pixels_per_meter = DISPLAY_SIZE / (2 * range_m)
    x_m = (x - DISPLAY_SIZE / 2) / pixels_per_meter
    y_m = (DISPLAY_SIZE / 2 - y) / pixels_per_meter
    latitude = center_latitude + math.degrees(y_m / EARTH_RADIUS_M)
    longitude = center_longitude + math.degrees(
        x_m / (EARTH_RADIUS_M * math.cos(math.radians(center_latitude)))
    )
    return latitude, longitude


def point_inside(point: tuple[float, float]) -> bool:
    """Prueft, ob ein Pixelpunkt innerhalb des runden Displays liegt."""
    distance_x = point[0] - DISPLAY_SIZE / 2
    distance_y = point[1] - DISPLAY_SIZE / 2
    return distance_x * distance_x + distance_y * distance_y <= (DISPLAY_SIZE / 2) ** 2


def distance_to_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Berechnet den Abstand eines Punkts zu einem Liniensegment."""
    segment_x = end[0] - start[0]
    segment_y = end[1] - start[1]
    length_squared = segment_x * segment_x + segment_y * segment_y
    if length_squared == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    factor = (
        (point[0] - start[0]) * segment_x + (point[1] - start[1]) * segment_y
    ) / length_squared
    factor = max(0.0, min(1.0, factor))
    closest = (start[0] + factor * segment_x, start[1] + factor * segment_y)
    return math.hypot(point[0] - closest[0], point[1] - closest[1])


def simplify_line(
    points: list[tuple[float, float]], tolerance: float
) -> list[tuple[float, float]]:
    """Reduziert eine Linie mit Douglas-Peucker."""
    if len(points) <= 2:
        return points

    maximum_distance = 0.0
    split_index = 0
    for index in range(1, len(points) - 1):
        distance = distance_to_segment(points[index], points[0], points[-1])
        if distance > maximum_distance:
            maximum_distance = distance
            split_index = index

    if maximum_distance > tolerance:
        first = simplify_line(points[: split_index + 1], tolerance)
        second = simplify_line(points[split_index:], tolerance)
        return first[:-1] + second
    return [points[0], points[-1]]


def split_inside_segments(
    points: Iterable[tuple[float, float]]
) -> list[list[tuple[float, float]]]:
    """Teilt Linien an der Kreisgrenze in darstellbare Teilstuecke."""
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for point in points:
        if point_inside(point):
            current.append(point)
        elif current:
            if len(current) >= 2:
                segments.append(current)
            current = []
    if len(current) >= 2:
        segments.append(current)
    return segments


def merge_connected_lines(
    lines: list[tuple[str, list[tuple[float, float]]]],
    tolerance: float = 2.0,
    max_heading_change: float = math.pi / 2,
) -> list[tuple[str, list[tuple[float, float]]]]:
    """Verbindet benachbarte Teilstuecke derselben Autobahn im Pixelraum."""
    merged = lines[:]
    changed = True
    while changed:
        changed = False
        for first_index, (first_motorway, first_line) in enumerate(merged):
            for second_index in range(first_index + 1, len(merged)):
                second_motorway, second_line = merged[second_index]
                if first_motorway != second_motorway:
                    continue

                combinations = (
                    (first_line, second_line),
                    (first_line, list(reversed(second_line))),
                    (list(reversed(first_line)), second_line),
                    (list(reversed(first_line)), list(reversed(second_line))),
                )
                valid_combinations = []
                for first_part, second_part in combinations:
                    distance = math.hypot(
                        first_part[-1][0] - second_part[0][0],
                        first_part[-1][1] - second_part[0][1],
                    )
                    if distance > tolerance:
                        continue
                    first_vector = (
                        first_part[-1][0] - first_part[-2][0],
                        first_part[-1][1] - first_part[-2][1],
                    )
                    second_vector = (
                        second_part[1][0] - second_part[0][0],
                        second_part[1][1] - second_part[0][1],
                    )
                    first_angle = math.atan2(first_vector[1], first_vector[0])
                    second_angle = math.atan2(second_vector[1], second_vector[0])
                    angle_difference = abs(first_angle - second_angle)
                    angle_difference = min(
                        angle_difference, 2 * math.pi - angle_difference
                    )
                    if angle_difference <= max_heading_change:
                        valid_combinations.append(
                            (angle_difference, first_part + second_part)
                        )

                if valid_combinations:
                    _, combined = min(valid_combinations, key=lambda item: item[0])
                    merged[first_index] = (first_motorway, combined)
                    del merged[second_index]
                    changed = True
                    break
                if changed:
                    break
            if changed:
                break
    return merged


def line_length(line: list[tuple[float, float]]) -> float:
    """Berechnet die Laenge einer Pixel-Linie."""
    return sum(
        math.hypot(line[index][0] - line[index - 1][0], line[index][1] - line[index - 1][1])
        for index in range(1, len(line))
    )


def resample_line(
    line: list[tuple[float, float]], sample_count: int = 16
) -> list[tuple[float, float]]:
    """Erzeugt gleichmaessig verteilte Vergleichspunkte auf einer Linie."""
    if len(line) <= 1:
        return line[:]
    lengths = [0.0]
    for index in range(1, len(line)):
        lengths.append(
            lengths[-1]
            + math.hypot(
                line[index][0] - line[index - 1][0],
                line[index][1] - line[index - 1][1],
            )
        )
    total_length = lengths[-1]
    if total_length == 0:
        return [line[0]] * sample_count

    samples = []
    for sample_index in range(sample_count):
        target = total_length * sample_index / (sample_count - 1)
        for index in range(1, len(line)):
            if lengths[index] < target:
                continue
            segment_length = lengths[index] - lengths[index - 1]
            if segment_length == 0:
                continue
            factor = (target - lengths[index - 1]) / segment_length
            samples.append(
                (
                    line[index - 1][0]
                    + factor * (line[index][0] - line[index - 1][0]),
                    line[index - 1][1]
                    + factor * (line[index][1] - line[index - 1][1]),
                )
            )
            break
    return samples


def average_line_distance(
    first: list[tuple[float, float]], second: list[tuple[float, float]]
) -> float:
    """Vergleicht zwei Linien in gleicher Laufrichtung im Pixelraum."""
    return sum(
        math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(first, second)
    ) / len(first)


def collapse_parallel_lines(
    lines: list[tuple[str, list[tuple[float, float]]]], max_distance: float = 2.5
) -> list[tuple[str, list[tuple[float, float]]]]:
    """Bildet eine Mittellinie aus nahen, parallelen Fahrbahngeometrien."""
    collapsed = lines[:]
    changed = True
    while changed:
        changed = False
        for first_index, (first_motorway, first_line) in enumerate(collapsed):
            first_length = line_length(first_line)
            if first_length == 0:
                continue
            first_samples = resample_line(first_line)
            for second_index in range(first_index + 1, len(collapsed)):
                second_motorway, second_line = collapsed[second_index]
                if first_motorway != second_motorway:
                    continue
                second_length = line_length(second_line)
                if second_length == 0:
                    continue
                length_ratio = min(first_length, second_length) / max(
                    first_length, second_length
                )
                if length_ratio < 0.55:
                    continue

                second_samples = resample_line(second_line)
                reverse_samples = list(reversed(second_samples))
                distance = min(
                    average_line_distance(first_samples, second_samples),
                    average_line_distance(first_samples, reverse_samples),
                )
                if distance > max_distance:
                    continue

                if average_line_distance(first_samples, second_samples) <= average_line_distance(
                    first_samples, reverse_samples
                ):
                    aligned = second_samples
                else:
                    aligned = reverse_samples
                maximum_distance = max(
                    math.hypot(first[0] - second[0], first[1] - second[1])
                    for first, second in zip(first_samples, aligned)
                )
                if maximum_distance > max_distance * 2.5:
                    continue
                midpoint = [
                    ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)
                    for first, second in zip(first_samples, aligned)
                ]
                collapsed[first_index] = (first_motorway, midpoint)
                del collapsed[second_index]
                changed = True
                break
            if changed:
                break
    return collapsed


def smooth_line(
    line: list[tuple[float, float]], passes: int = 1
) -> list[tuple[float, float]]:
    """Glaettet Display-Linien, ohne deren Endpunkte zu verschieben."""
    smoothed = line[:]
    for _ in range(passes):
        if len(smoothed) < 3:
            break
        smoothed = [
            smoothed[0],
            *[
                (
                    (smoothed[index - 1][0] + 2 * smoothed[index][0] + smoothed[index + 1][0])
                    / 4,
                    (smoothed[index - 1][1] + 2 * smoothed[index][1] + smoothed[index + 1][1])
                    / 4,
                )
                for index in range(1, len(smoothed) - 1)
            ],
            smoothed[-1],
        ]
    return smoothed


def select_representative_lines(
    lines: list[tuple[str, list[tuple[float, float]]]],
    selection: str,
    max_heading_change_deg: float,
) -> list[tuple[str, list[tuple[float, float]]]]:
    """Waehlt pro Autobahn den besten sichtbaren zusammenhaengenden Verlauf."""
    by_motorway: dict[str, list[list[tuple[float, float]]]] = {}
    for motorway, line in lines:
        by_motorway.setdefault(motorway, []).append(line)

    selected_lines: list[tuple[str, list[tuple[float, float]]]] = []
    max_angle = math.radians(max_heading_change_deg)
    connection_tolerance = 2.0

    for motorway, motorway_lines in by_motorway.items():
        endpoints = [
            point
            for line in motorway_lines
            for point in (line[0], line[-1])
        ]
        x_range = max(point[0] for point in endpoints) - min(
            point[0] for point in endpoints
        )
        y_range = max(point[1] for point in endpoints) - min(
            point[1] for point in endpoints
        )
        direction = selection
        if direction == "auto":
            direction = "north" if y_range >= x_range else "east"

        visible_endpoints = [point for point in endpoints if point_inside(point)]
        anchor_candidates = visible_endpoints or endpoints
        if direction == "north":
            anchor = min(anchor_candidates, key=lambda point: point[1])
        else:
            anchor = max(anchor_candidates, key=lambda point: point[0])

        def trace_route(start_index: int, reverse: bool):
            start_line = motorway_lines[start_index]
            route = list(reversed(start_line)) if reverse else start_line[:]
            unused = {
                index for index in range(len(motorway_lines)) if index != start_index
            }

            while unused and len(route) >= 2:
                current_end = route[-1]
                current_vector = (
                    route[-1][0] - route[-2][0],
                    route[-1][1] - route[-2][1],
                )
                current_angle = math.atan2(current_vector[1], current_vector[0])
                candidates = []
                for index in unused:
                    line = motorway_lines[index]
                    for oriented in (line, list(reversed(line))):
                        distance = math.hypot(
                            oriented[0][0] - current_end[0],
                            oriented[0][1] - current_end[1],
                        )
                        if distance > connection_tolerance:
                            continue
                        vector = (
                            oriented[1][0] - oriented[0][0],
                            oriented[1][1] - oriented[0][1],
                        )
                        angle = abs(current_angle - math.atan2(vector[1], vector[0]))
                        angle = min(angle, 2 * math.pi - angle)
                        if angle <= max_angle:
                            candidates.append((distance + angle * 2, index, oriented))
                if not candidates:
                    break
                _, selected_index, selected_line = min(
                    candidates, key=lambda item: item[0]
                )
                route.extend(selected_line[1:])
                unused.remove(selected_index)
            return route

        def route_score(route: list[tuple[float, float]]) -> tuple[float, float, float]:
            visible_length = 0.0
            total_length = line_length(route)
            for index in range(1, len(route)):
                start = route[index - 1]
                end = route[index]
                if point_inside(start) or point_inside(end):
                    visible_length += math.hypot(
                        end[0] - start[0], end[1] - start[1]
                    )
            start_distance = math.hypot(route[0][0] - anchor[0], route[0][1] - anchor[1])
            return visible_length, total_length, -start_distance

        possible_routes = [
            (route_score(route), route)
            for index in range(len(motorway_lines))
            for route in (trace_route(index, False), trace_route(index, True))
        ]
        _, best_route = max(possible_routes, key=lambda item: item[0])
        selected_lines.append((motorway, best_route))

    return selected_lines


def select_routes_by_osm_nodes(
    source_lines: list[tuple[str, list[tuple[float, float]], list[int]]],
    center_latitude: float,
    center_longitude: float,
    range_km: int,
    max_heading_change_deg: float,
) -> list[tuple[str, list[tuple[float, float]]]]:
    """Verbindet OSM-Ways ueber gemeinsame Node-IDs zu Hauptverlaeufen."""
    by_motorway: dict[str, list[tuple[list[tuple[float, float]], list[int]]]] = {}
    for motorway, coordinates, nodes in source_lines:
        by_motorway.setdefault(motorway, []).append((coordinates, nodes))

    range_m = range_km * 1000
    max_angle = math.radians(max_heading_change_deg)
    routes: list[tuple[str, list[tuple[float, float]]]] = []

    for motorway, ways in by_motorway.items():
        node_map: dict[int, list[int]] = {}
        for index, (_, nodes) in enumerate(ways):
            node_map.setdefault(nodes[0], []).append(index)
            node_map.setdefault(nodes[-1], []).append(index)

        def trace(start_index: int, reverse: bool):
            coordinates, nodes = ways[start_index]
            route = list(reversed(coordinates)) if reverse else coordinates[:]
            current_nodes = list(reversed(nodes)) if reverse else nodes[:]
            used = {start_index}

            while len(current_nodes) >= 2:
                current_node = current_nodes[-1]
                current_vector = (
                    route[-1][1] - route[-2][1],
                    route[-1][0] - route[-2][0],
                )
                current_angle = math.atan2(current_vector[1], current_vector[0])
                candidates = []
                for candidate_index in node_map.get(current_node, []):
                    if candidate_index in used:
                        continue
                    candidate_coordinates, candidate_nodes = ways[candidate_index]
                    if candidate_nodes[0] == current_node:
                        oriented_coordinates = candidate_coordinates
                        oriented_nodes = candidate_nodes
                    else:
                        oriented_coordinates = list(reversed(candidate_coordinates))
                        oriented_nodes = list(reversed(candidate_nodes))
                    vector = (
                        oriented_coordinates[1][1] - oriented_coordinates[0][1],
                        oriented_coordinates[1][0] - oriented_coordinates[0][0],
                    )
                    angle = abs(current_angle - math.atan2(vector[1], vector[0]))
                    angle = min(angle, 2 * math.pi - angle)
                    if angle <= max_angle:
                        candidates.append((angle, candidate_index, oriented_coordinates, oriented_nodes))
                if not candidates:
                    break
                _, selected_index, selected_coordinates, selected_nodes = min(
                    candidates, key=lambda item: item[0]
                )
                route.extend(selected_coordinates[1:])
                current_nodes.extend(selected_nodes[1:])
                used.add(selected_index)
            return route

        def route_score(route: list[tuple[float, float]]) -> tuple[float, float, float]:
            visible_length = 0.0
            total_length = 0.0
            projected = [
                project_to_pixels(
                    latitude,
                    longitude,
                    center_latitude,
                    center_longitude,
                    range_m,
                )
                for latitude, longitude in route
            ]
            for index in range(1, len(projected)):
                length = math.hypot(
                    projected[index][0] - projected[index - 1][0],
                    projected[index][1] - projected[index - 1][1],
                )
                total_length += length
                if point_inside(projected[index]) or point_inside(projected[index - 1]):
                    visible_length += length
            center_distance = min(
                math.hypot(point[0] - DISPLAY_SIZE / 2, point[1] - DISPLAY_SIZE / 2)
                for point in projected
            )
            # Prefer the route reaching furthest into the map; use length as tie-breaker.
            return -center_distance, visible_length, total_length

        possible_routes = [
            trace(index, reverse)
            for index in range(len(ways))
            for reverse in (False, True)
        ]
        best_route = max(possible_routes, key=route_score)
        routes.append((motorway, best_route))

    return routes


def motorway_from_filename(path: Path) -> str:
    """Ermittelt die A- oder B-Strassenkennung aus einem Dateinamen."""
    match = re.match(r"([ab]\d+)_motorways\.json$", path.name, re.I)
    return match.group(1).upper() if match else path.stem


def load_lines(
    input_dir: Path,
) -> list[tuple[str, list[tuple[float, float]], list[int]]]:
    """Liest alle Overpass-Way-Geometrien aus dem Eingabeordner."""
    lines: list[tuple[str, list[tuple[float, float]], list[int]]] = []
    files = sorted(input_dir.glob("*_motorways.json"))
    if not files:
        raise FileNotFoundError(
            f"Keine *_motorways.json-Dateien in {input_dir.resolve()} gefunden."
        )

    for path in files:
        with path.open("r", encoding="utf-8") as input_file:
            data = json.load(input_file)
        motorway = motorway_from_filename(path)
        for element in data.get("elements", []):
            geometry = element.get("geometry", [])
            coordinates = [
                (float(point["lat"]), float(point["lon"]))
                for point in geometry
                if "lat" in point and "lon" in point
            ]
            if len(coordinates) >= 2:
                nodes = [int(node) for node in element.get("nodes", [])]
                if len(nodes) == len(coordinates):
                    lines.append((motorway, coordinates, nodes))
    return lines


def load_cities(path: Path) -> list[tuple[str, float, float]]:
    """Liest MapCity-Initialisierungen aus einer C++-Datei."""
    city_pattern = re.compile(
        r'\{\s*"([^"]+)"\s*,\s*([-+]?\d+(?:\.\d+)?)f?\s*,\s*'
        r'([-+]?\d+(?:\.\d+)?)f?\s*\}'
    )
    content = path.read_text(encoding="utf-8")
    return [
        (label, float(latitude), float(longitude))
        for label, latitude, longitude in city_pattern.findall(content)
    ]


def process_lines(
    source_lines: list[tuple[str, list[tuple[float, float]], list[int]]],
    center_latitude: float,
    center_longitude: float,
    range_km: int,
    refinement_factor: float,
    max_heading_change_deg: float,
    min_segment_length_m: float,
    carriageway_selection: str,
) -> list[dict[str, object]]:
    """Projiziert, beschneidet und reduziert die Overpass-Linien."""
    range_m = range_km * 1000
    base_tolerance = DISPLAY_SIZE / (2 * range_m) * 125
    tolerance = max(0.25, base_tolerance / refinement_factor)
    candidate_lines: list[tuple[str, list[tuple[float, float]]]] = []
    reduced_lines: list[dict[str, object]] = []
    seen: set[tuple[str, tuple[tuple[int, int], ...]]] = set()

    graph_routes = select_routes_by_osm_nodes(
        source_lines,
        center_latitude,
        center_longitude,
        range_km,
        max_heading_change_deg,
    )
    for motorway, coordinates in graph_routes:
        pixels = [
            project_to_pixels(
                latitude,
                longitude,
                center_latitude,
                center_longitude,
                range_m,
            )
            for latitude, longitude in coordinates
        ]
        for segment in split_inside_segments(pixels):
            simplified = simplify_line(segment, tolerance)
            rounded = [(round(x, 1), round(y, 1)) for x, y in simplified]
            if len(rounded) < 2:
                continue
            candidate_lines.append((motorway, rounded))

    merge_tolerance = max(0.15, DISPLAY_SIZE / (2 * range_m) * 25)
    merged_lines = merge_connected_lines(
        candidate_lines,
        merge_tolerance,
        math.radians(max_heading_change_deg),
    )
    # The OSM-node graph has already selected one carriageway. Keep its
    # connected visible pieces instead of applying a second pixel heuristic.
    centerline_lines = merged_lines
    for motorway, rounded in centerline_lines:
        rounded = smooth_line(rounded)
        simplified = simplify_line(rounded, tolerance)
        rounded = [(round(x, 1), round(y, 1)) for x, y in simplified]
        minimum_length_pixels = max(
            MIN_DISPLAY_LINE_LENGTH,
            min_segment_length_m * DISPLAY_SIZE / (2 * range_m),
        )
        if len(rounded) < 2 or line_length(rounded) < minimum_length_pixels:
            continue
        key = (motorway, tuple((round(x), round(y)) for x, y in rounded))
        reverse_key = (motorway, tuple(reversed(key[1])))
        if key in seen or reverse_key in seen:
            continue
        seen.add(key)
        reduced_lines.append(
            {
                "motorway": motorway,
                "coordinates": [
                    list(
                        pixels_to_coordinates(
                            x,
                            y,
                            center_latitude,
                            center_longitude,
                            range_m,
                        )
                    )
                    for x, y in rounded
                ],
            }
        )
    return reduced_lines


def write_output(path: Path, args: argparse.Namespace, lines: list[dict[str, object]]) -> None:
    """Schreibt das Ergebnis als C++-Header oder optional als JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "cpp":
        lines_by_motorway: dict[str, list[list[float]]] = {}
        for line in lines:
            motorway = str(line["motorway"])
            coordinates = line["coordinates"]
            lines_by_motorway.setdefault(motorway, []).append(coordinates)

        cpp_lines = [
            "#pragma once",
            "",
            '#include "MapTypes.h"',
            "",
            "// Generated by reduce_motorways_for_display.py",
            "// Coordinates are latitude/longitude in decimal degrees.",
            "// Map data (c) OpenStreetMap contributors, ODbL.",
            "",
        ]
        road_entries: list[tuple[str, str, str]] = []
        for motorway in sorted(lines_by_motorway):
            identifier = re.sub(r"[^A-Za-z0-9_]", "_", motorway)
            road_lines = sorted(
                lines_by_motorway[motorway], key=len, reverse=True
            )
            for line_index, coordinates in enumerate(road_lines):
                suffix = "" if line_index == 0 else f"_{line_index}"
                array_name = f"kRoad{identifier}{suffix}"
                cpp_lines.append(f"// {motorway}, simplified orientation centreline.")
                cpp_lines.append(f"constexpr MapPoint {array_name}[] = {{")
                for latitude, longitude in coordinates:
                    cpp_lines.append(f"    {{{latitude:.6f}f, {longitude:.6f}f}},")
                cpp_lines.extend(["};", ""])
                road_kind = (
                    "kPrimary" if motorway.upper().startswith("B") else "kMotorway"
                )
                road_entries.append((motorway, array_name, road_kind))

        cpp_lines.extend(
            [
                "constexpr MapRoad kMapRoads[] = {",
            ]
        )
        for motorway, array_name, road_kind in road_entries:
            cpp_lines.extend(
                [
                    f'    {{"{motorway}", {array_name}, '
                    f"sizeof({array_name}) / sizeof({array_name}[0]),",
                    "    MapRoadKind::" + road_kind + "},",
                ]
            )
        cpp_lines.extend(
            [
                "};",
                "",
                "constexpr size_t kMapRoadCount =",
                "    sizeof(kMapRoads) / sizeof(kMapRoads[0]);",
                "",
            ]
        )
        path.write_text("\n".join(cpp_lines), encoding="utf-8")
        return

    output = {
        "format": "motorway-display-v2",
        "display": {"width": DISPLAY_SIZE, "height": DISPLAY_SIZE, "shape": "circle"},
        "center": {"latitude": args.latitude, "longitude": args.longitude},
        "range_km": args.range_km,
        "line_count": len(lines),
        "lines": lines,
    }
    path.write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def load_cpp_roads(path: Path) -> dict[str, list[tuple[float, float]]]:
    """Liest die reduzierten MapPoint-Arrays aus dem generierten Header."""
    content = path.read_text(encoding="ascii")
    array_pattern = re.compile(
        r"constexpr\s+MapPoint\s+kRoad([A-Za-z0-9_]+)\[\]\s*=\s*\{(.*?)\};",
        re.DOTALL,
    )
    point_pattern = re.compile(
        r"\{\s*([-+]?\d+(?:\.\d+)?)f\s*,\s*"
        r"([-+]?\d+(?:\.\d+)?)f\s*\}"
    )
    roads: dict[str, list[tuple[float, float]]] = {}
    for motorway, array_content in array_pattern.findall(content):
        roads[motorway] = [
            (float(latitude), float(longitude))
            for latitude, longitude in point_pattern.findall(array_content)
        ]
    return roads


def write_svg(
    path: Path,
    args: argparse.Namespace,
    roads: dict[str, list[list[tuple[float, float]]]],
    cities: list[tuple[str, float, float]],
) -> None:
    """Erzeugt eine 240x240-SVG-Vorschau der reduzierten Autobahnen."""
    range_m = args.range_km * 1000
    svg_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" '
        'viewBox="0 0 240 240">',
        "  <title>Autobahnkarte</title>",
        "  <defs>",
        '    <clipPath id="map-area"><circle cx="120" cy="120" r="119" /></clipPath>',
        "  </defs>",
        '  <rect width="240" height="240" fill="none" />',
        '  <g stroke="#238b45" fill="none">',
        '    <line x1="1" y1="120" x2="239" y2="120" stroke-width="0.7" />',
        '    <line x1="120" y1="1" x2="120" y2="239" stroke-width="0.7" />',
    ]

    for radius_km in range(5, args.range_km, 5):
        radius_pixels = DISPLAY_SIZE / 2 * radius_km / args.range_km
        svg_lines.append(
            f'    <circle cx="120" cy="120" r="{radius_pixels:.2f}" '
            'stroke-width="0.7" stroke-dasharray="3,3" />'
        )
    svg_lines.extend(
        [
            "  </g>",
            '  <g clip-path="url(#map-area)" fill="none" '
            'stroke-linecap="round" stroke-linejoin="round">',
        ]
    )

    for motorway in sorted(roads):
        for road_line in roads[motorway]:
            points = []
            for latitude, longitude in road_line:
                x, y = project_to_pixels(
                    latitude,
                    longitude,
                    args.latitude,
                    args.longitude,
                    range_m,
                )
                points.append(f"{x:.1f},{y:.1f}")
            if len(points) >= 2:
                point_string = " ".join(points)
                road_color = (
                    FEDERAL_ROAD_COLOR
                    if motorway.upper().startswith("B")
                    else MOTORWAY_COLOR
                )
                svg_lines.append(
                    f'    <polyline points="{point_string}" '
                    f'stroke="{road_color}" stroke-width="1" />'
                )

    svg_lines.extend(
        [
            "  </g>",
            '  <g clip-path="url(#map-area)" fill="#b8b8b8" stroke="none">',
        ]
    )
    range_m = args.range_km * 1000
    for label, latitude, longitude in cities:
        x, y = project_to_pixels(
            latitude,
            longitude,
            args.latitude,
            args.longitude,
            range_m,
        )
        if not point_inside((x, y)):
            continue
        escaped_label = html.escape(label)
        svg_lines.extend(
            [
                f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="1.5" />',
                f'    <text x="{x + 3:.1f}" y="{y - 2:.1f}" '
                'font-family="Arial, sans-serif" font-size="5" '
                f'fill="#b8b8b8">{escaped_label}</text>',
            ]
        )

    svg_lines.extend(
        [
            "  </g>",
        ]
    )

    svg_lines.extend(
        [
            '  <circle cx="120" cy="120" r="3" fill="#d00000" stroke="white" '
            'stroke-width="0.8" />',
            '  <circle cx="120" cy="120" r="119" fill="none" stroke="black" '
            'stroke-width="1.5" />',
            "</svg>",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(svg_lines), encoding="utf-8")


def write_overview_svg(path: Path) -> None:
    """Erzeugt eine 3x2-Uebersicht der sechs reduzierten Einzel-SVGs."""
    panel_width = 240
    panel_height = 270
    columns = 3
    rows = 2
    overview_width = panel_width * columns
    overview_height = panel_height * rows
    svg_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{overview_width}" '
        f'height="{overview_height}" viewBox="0 0 {overview_width} {overview_height}">',
        "  <rect width=\"100%\" height=\"100%\" fill=\"#eeeeee\" />",
    ]
    for index, range_km in enumerate(DISPLAY_RANGES_KM):
        column = index % columns
        row = index // columns
        x = column * panel_width
        y = row * panel_height
        svg_lines.extend(
            [
                f'  <rect x="{x + 4}" y="{y + 4}" width="232" height="262" '
                'fill="white" stroke="#999999" />',
                f'  <text x="{x + 10}" y="{y + 20}" font-family="Arial, sans-serif" '
                f'font-size="12" fill="#333333">{range_km} km</text>',
                f'  <image x="{x}" y="{y + 25}" width="240" height="240" '
                f'href="motorway_map_{range_km}km.svg" />',
            ]
        )
    svg_lines.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(svg_lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        if not -90 <= args.latitude <= 90:
            raise ValueError("Der Breitengrad muss zwischen -90 und 90 liegen.")
        if not -180 <= args.longitude <= 180:
            raise ValueError("Der Laengengrad muss zwischen -180 und 180 liegen.")
        if args.refinement_factor <= 0:
            raise ValueError("Der Verfeinerungsfaktor muss groesser als 0 sein.")
        if not 0 < args.max_heading_change_deg <= 180:
            raise ValueError(
                "Der maximale Richtungswechsel muss zwischen 0 und 180 Grad liegen."
            )
        if args.min_segment_length_m <= 0:
            raise ValueError("Die Mindestsegmentlaenge muss groesser als 0 sein.")

        print(f"Lese Autobahn-Dateien aus {args.input_dir.resolve()} ...")
        source_lines = load_lines(args.input_dir)
        print(f"{len(source_lines)} Linien eingelesen.")
        cities = load_cities(args.cities_file)
        print(f"{len(cities)} Staedte aus {args.cities_file} eingelesen.")
        print(f"Verfeinerungsfaktor: {args.refinement_factor:g}")
        print(f"Maximaler Richtungswechsel: {args.max_heading_change_deg:g} Grad")
        print(f"Mindestsegmentlaenge: {args.min_segment_length_m:g} m")
        print(f"Fahrtrichtungsauswahl: {args.carriageway_selection}")
        raw_roads: dict[str, list[list[tuple[float, float]]]] = {}
        for motorway, coordinates, _ in source_lines:
            raw_roads.setdefault(motorway, []).append(coordinates)

        selected_svg_range = args.range_km
        header_range = 30
        args.range_km = header_range
        print(f"\nErzeuge einzigen Strassen-Header fuer {header_range} km ...")
        lines = process_lines(
            source_lines,
            args.latitude,
            args.longitude,
            header_range,
            args.refinement_factor,
            args.max_heading_change_deg,
            args.min_segment_length_m,
            args.carriageway_selection,
        )
        suffix = "h" if args.format == "cpp" else "json"
        output = args.output or args.output_dir / f"motorway_map_{header_range}km.{suffix}"
        write_output(output, args, lines)
        if args.format == "cpp":
            reduced_roads = {
                motorway: [coordinates]
                for motorway, coordinates in load_cpp_roads(output).items()
            }
            print(
                f"{len(reduced_roads)} reduzierte Strassen aus {output.name} gelesen."
            )
        else:
            reduced_roads = {
                str(line["motorway"]): [
                    [tuple(point) for point in line["coordinates"]]
                ]
                for line in lines
            }

        for current_range in DISPLAY_RANGES_KM:
            args.range_km = current_range
            print(f"\nErzeuge Display-Darstellungen fuer {current_range} km ...")
            svg_output = (
                args.svg_output
                if current_range == selected_svg_range and args.svg_output
                else args.output_dir / f"motorway_map_{current_range}km.svg"
            )
            write_svg(svg_output, args, reduced_roads, cities)
            raw_svg_output = (
                args.raw_svg_output
                if current_range == selected_svg_range and args.raw_svg_output
                else args.output_dir / f"motorway_map_{current_range}km_raw.svg"
            )
            write_svg(raw_svg_output, args, raw_roads, cities)
            print(f"SVG-Visualisierung gespeichert: {svg_output.resolve()}")
            print(f"SVG-Rohdaten gespeichert: {raw_svg_output.resolve()}")
        overview_output = args.overview_svg_output or (
            args.output_dir / "motorway_map_overview.svg"
        )
        write_overview_svg(overview_output)
        print(f"SVG-Uebersicht gespeichert: {overview_output.resolve()}")
        print(f"{len(lines)} reduzierte Linien gespeichert: {output.resolve()}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Fehler: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
