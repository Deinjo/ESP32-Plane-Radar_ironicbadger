# Plane Radar Simulator

Browser-based simulator for the 240 x 240 ESP32 Plane Radar display. The browser canvas renders at 720 x 720 pixels with a 3x scale factor for smoother presentation.

## Start

From the repository root, run:

```powershell
python tools/radar_simulator/server.py
```

Open `http://localhost:8080/tools/radar_simulator/` in a browser. The server serves the repository root, loads the real motorway and large-airport/runway data, and provides the local ADS-B proxy. The proxy also enriches callsigns with cached route data and airport municipality names from ADSBDB, matching the firmware's route display behavior. If the map, airport data or API cannot be loaded, the simulator falls back to representative mock geometry or mock aircraft.

## Windows executable

From the repository root, run:

```powershell
powershell -ExecutionPolicy Bypass -File tools/radar_simulator/build_windows.ps1
```

The result is created at:

```text
dist/PlaneRadarSimulator.exe
```

Double-clicking the executable starts the local proxy and opens the simulator in the default browser. Keep the console window open while using the simulator. The executable contains the simulator files, the motorway map and the airport/runway data.

The simulator is intentionally framework-free. The browser only talks to the local server; the optional server-side proxy fetches live ADS-B data. It loads the local firmware map header when served from the repository root and falls back to deterministic mock geometry or aircraft if data is unavailable. The setup panel mirrors the firmware options for coordinates, units, footer/weather, temperature, altitude, clock format, text size, range, layers, colors and night mode. The rendering pipeline includes radar range projection and circular segment clipping.
