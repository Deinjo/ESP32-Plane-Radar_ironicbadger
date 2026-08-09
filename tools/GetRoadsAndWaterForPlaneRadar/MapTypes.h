#pragma once

#include <cstddef>
#include <cstdint>

struct MapPoint {
    float lat;
    float lon;
};

enum class MapRoadKind : uint8_t {
    kMotorway,
    kPrimary,
};

struct MapRoad {
    const char* id;
    const MapPoint* points;
    size_t point_count;
    MapRoadKind kind;
};

enum class MapWaterKind : uint8_t {
    kArea,
    kRiver,
    kCanal,
};

struct MapWater {
    const char* id;
    const MapPoint* points;
    size_t point_count;
    MapWaterKind kind;
};
