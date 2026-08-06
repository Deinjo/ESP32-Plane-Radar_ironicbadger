import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("Usage:")
        print("  python tools/generate_road_cpp.py tools/roads/a45_centerline.json")
        raise SystemExit(1)

    input_path = Path(sys.argv[1])

    with input_path.open("r", encoding="utf-8") as file:
        road = json.load(file)

    name = road["name"]
    points = road["points"]

    cpp_name = "kRoad" + "".join(
        part.capitalize() for part in name.replace("-", " ").split()
    )

    print(f"// {name}, simplified orientation centreline.")
    print("// Map data © OpenStreetMap contributors, ODbL.")
    print(f"constexpr MapPoint {cpp_name}[] = {{")

    for lat, lon in points:
        print(f"    {{{lat:.6f}f, {lon:.6f}f}},")

    print("};")
    print()
    print(
        f'{{"{name}", {cpp_name}, sizeof({cpp_name}) / sizeof({cpp_name}[0]),'
    )
    print(" MapRoadKind::kMotorway},")
    print()
    print(f"Generated {len(points)} points.")


if __name__ == "__main__":
    main()