import json
import math
import sys
from pathlib import Path


# Your local radar centre.
CENTER_LAT = 51.4841569828169
CENTER_LON = 7.4157398724495245

# Keep map geometry within this radius around the radar centre.
RADIUS_KM = 50.0

# Small safety margin: ways that cross the edge are not cut too early.
MARGIN_KM = 2.0

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two WGS84 coordinates."""
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2.0) ** 2
    )

    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def line_has_point_in_radius(coordinates, max_distance_km):
    """Return True if at least one GeoJSON point is near the radar centre.

    GeoJSON stores coordinates as [longitude, latitude].
    """
    for lon, lat in coordinates:
        if haversine_km(CENTER_LAT, CENTER_LON, lat, lon) <= max_distance_km:
            return True

    return False


def keep_geometry(geometry, max_distance_km):
    """Keep a LineString or relevant lines of a MultiLineString."""
    if not geometry:
        return None

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])

    if geometry_type == "LineString":
        if line_has_point_in_radius(coordinates, max_distance_km):
            return geometry
        return None

    if geometry_type == "MultiLineString":
        kept_lines = [
            line
            for line in coordinates
            if line_has_point_in_radius(line, max_distance_km)
        ]

        if not kept_lines:
            return None

        return {
            "type": "MultiLineString",
            "coordinates": kept_lines,
        }

    return None


def main():
    if len(sys.argv) != 3:
        print("Usage:")
        print(
            "  python tools/filter_geojson_radius.py "
            "tools/input/a45_dortmund_hagen.geojson "
            "tools/output/a45_50km.geojson"
        )
        raise SystemExit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    with input_path.open("r", encoding="utf-8") as file:
        source = json.load(file)

    max_distance_km = RADIUS_KM + MARGIN_KM
    kept_features = []

    for feature in source.get("features", []):
        geometry = keep_geometry(feature.get("geometry"), max_distance_km)

        if geometry is None:
            continue

        kept_feature = {
            "type": "Feature",
            "properties": feature.get("properties", {}),
            "geometry": geometry,
        }

        # Keep the OSM way ID, if it exists.
        if "id" in feature:
            kept_feature["id"] = feature["id"]

        kept_features.append(kept_feature)

    output = {
        "type": "FeatureCollection",
        "generator": "filter_geojson_radius.py",
        "metadata": {
            "center_lat": CENTER_LAT,
            "center_lon": CENTER_LON,
            "radius_km": RADIUS_KM,
            "margin_km": MARGIN_KM,
            "attribution": "Map data © OpenStreetMap contributors, ODbL",
        },
        "features": kept_features,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print(f"Input features:  {len(source.get('features', []))}")
    print(f"Kept features:   {len(kept_features)}")
    print(f"Radar centre:    {CENTER_LAT:.6f}, {CENTER_LON:.6f}")
    print(f"Radius:          {RADIUS_KM:.1f} km (+ {MARGIN_KM:.1f} km margin)")
    print(f"Output file:     {output_path}")


if __name__ == "__main__":
    main()