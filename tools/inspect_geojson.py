import json
import sys
from pathlib import Path


def iter_lines(geometry):
    """Yield LineString coordinate lists from GeoJSON geometry objects."""
    if not geometry:
        return

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])

    if geometry_type == "LineString":
        yield coordinates

    elif geometry_type == "MultiLineString":
        yield from coordinates


def main():
    if len(sys.argv) != 2:
        print("Usage:")
        print("  python tools/inspect_geojson.py path/to/file.geojson")
        raise SystemExit(1)

    path = Path(sys.argv[1])

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    features = data.get("features", [])
    print(f"File:     {path}")
    print(f"Features: {len(features)}")
    print()

    line_count = 0
    point_count = 0

    for feature_index, feature in enumerate(features):
        properties = feature.get("properties", {})
        geometry = feature.get("geometry")

        for line_index, line in enumerate(iter_lines(geometry)):
            if not line:
                continue

            line_count += 1
            point_count += len(line)

            # GeoJSON coordinate order is [longitude, latitude].
            first_lon, first_lat = line[0]
            last_lon, last_lat = line[-1]

            print(
                f"Feature {feature_index:3d}, line {line_index}: "
                f"{len(line):3d} points | "
                f"({first_lat:.6f}, {first_lon:.6f}) -> "
                f"({last_lat:.6f}, {last_lon:.6f})"
            )

            if properties:
                ref = properties.get("ref", "")
                name = properties.get("name", "")
                osm_id = properties.get("@id", properties.get("id", ""))

                print(
                    f"    id={osm_id}  ref={ref!r}  name={name!r}"
                )

    print()
    print(f"Total line strings: {line_count}")
    print(f"Total points:       {point_count}")


if __name__ == "__main__":
    main()