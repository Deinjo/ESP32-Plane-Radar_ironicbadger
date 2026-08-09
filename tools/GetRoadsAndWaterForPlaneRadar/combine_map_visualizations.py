#!/usr/bin/env python3
"""Kombiniert Straßen- und Wasser-SVGs je Zoomstufe und als Übersicht."""

from __future__ import annotations

import argparse
from pathlib import Path

from reduce_motorways_for_display import DISPLAY_RANGES_KM


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("display_output"))
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def write_combined(path: Path, range_km: int) -> None:
    water_name = f"water_map_{range_km}km.svg"
    roads_name = f"motorway_map_{range_km}km.svg"
    content = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240">',
            '  <rect width="240" height="240" fill="white" />',
            f'  <image href="{water_name}" x="0" y="0" width="240" height="240" />',
            f'  <image href="{roads_name}" x="0" y="0" width="240" height="240" />',
            "</svg>",
        ]
    )
    path.write_text(content, encoding="utf-8")


def write_overview(path: Path) -> None:
    panel_width = 240
    panel_height = 270
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="540" viewBox="0 0 720 540">',
        '  <rect width="720" height="540" fill="#eeeeee" />',
    ]
    for index, range_km in enumerate(DISPLAY_RANGES_KM):
        x = index % 3 * panel_width
        y = index // 3 * panel_height
        lines.extend(
            [
                f'  <rect x="{x + 4}" y="{y + 4}" width="232" height="262" fill="white" stroke="#999999" />',
                f'  <text x="{x + 10}" y="{y + 20}" font-family="Arial, sans-serif" font-size="12" fill="#333333">{range_km} km</text>',
                f'  <image href="water_map_{range_km}km.svg" x="{x}" y="{y + 25}" width="240" height="240" />',
                f'  <image href="motorway_map_{range_km}km.svg" x="{x}" y="{y + 25}" width="240" height="240" />',
            ]
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or args.input_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for range_km in DISPLAY_RANGES_KM:
        write_combined(output_dir / f"map_combined_{range_km}km.svg", range_km)
    write_overview(output_dir / "map_combined_overview.svg")
    print(f"Kombinierte SVGs gespeichert: {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
