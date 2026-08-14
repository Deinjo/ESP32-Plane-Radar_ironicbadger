"""Local static server and CORS-free proxy for live ADS-B simulator data."""

import json
import os
import sys
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    ROOT = sys._MEIPASS
else:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
API_BASE = "https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{dist}"
ROUTE_API = "https://api.adsbdb.com/v0/callsign/{callsign}"
ROUTE_CACHE = {}


class SimulatorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        if urlparse(self.path).path == "/api/aircraft":
            self.handle_aircraft()
            return
        super().do_GET()

    def handle_aircraft(self):
        query = parse_qs(urlparse(self.path).query)
        try:
            lat = float(query.get("lat", ["51.483004"])[0])
            lon = float(query.get("lon", ["7.415811"])[0])
            radius_km = min(50.0, max(1.0, float(query.get("range", ["25"])[0])))
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError("coordinates out of range")
        except ValueError:
            self.send_json({"error": "invalid location"}, 400)
            return

        distance_nm = radius_km / 1.852
        url = API_BASE.format(lat=f"{lat:.6f}", lon=f"{lon:.6f}", dist=f"{distance_nm:.1f}")
        request = Request(url, headers={"User-Agent": "ESP32-Plane-Radar-simulator/1.0"})
        try:
            with urlopen(request, timeout=8) as response:
                source = json.load(response)
            aircraft = source.get("ac", []) if isinstance(source, dict) else []
            self.enrich_routes(aircraft)
            self.send_json({"aircraft": aircraft, "source": "adsb.fi"})
        except Exception as error:
            self.send_json({"error": str(error)}, 502)

    @staticmethod
    def enrich_routes(aircraft):
        # Keep enrichment deliberately bounded. The ADS-B endpoint is polled
        # often, while route data can be cached for hours.
        lookups = 0
        now = time.time()
        for plane in aircraft:
            callsign = str(plane.get("flight", "")).strip()
            if not callsign or lookups >= 6:
                continue
            cached = ROUTE_CACHE.get(callsign)
            if cached and now - cached[0] < 6 * 60 * 60:
                if cached[1]:
                    plane["route"] = cached[1]
                if cached[2]:
                    plane["route_type"] = cached[2]
                if cached[3]:
                    plane["route_origin"] = cached[3]
                if cached[4]:
                    plane["route_destination"] = cached[4]
                continue
            route, aircraft_type, origin_name, destination_name = "", "", "", ""
            try:
                route_url = ROUTE_API.format(callsign=callsign)
                request = Request(route_url, headers={"User-Agent": "ESP32-Plane-Radar-simulator/1.0"})
                with urlopen(request, timeout=3) as response:
                    payload = json.load(response)
                response_data = payload.get("response", {})
                flight_route = response_data.get("flightroute", {})
                origin = flight_route.get("origin", {})
                destination = flight_route.get("destination", {})
                origin_code = origin.get("iata_code") or origin.get("icao_code", "")
                destination_code = destination.get("iata_code") or destination.get("icao_code", "")
                origin_name = origin.get("municipality") or origin.get("name") or origin_code
                destination_name = destination.get("municipality") or destination.get("name") or destination_code
                if origin_code and destination_code:
                    route = f"{origin_code}-{destination_code}"
                aircraft_type = response_data.get("aircraft", {}).get("icao_type", "")
            except Exception:
                pass
            ROUTE_CACHE[callsign] = (now, route, aircraft_type, origin_name, destination_name)
            if route:
                plane["route"] = route
            if aircraft_type:
                plane["route_type"] = aircraft_type
            if origin_name:
                plane["route_origin"] = origin_name
            if destination_name:
                plane["route_destination"] = destination_name
            lookups += 1

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8080), SimulatorHandler)
    url = "http://localhost:8080/tools/radar_simulator/"
    print(f"Plane Radar simulator: {url}")
    print("Live ADS-B proxy: http://localhost:8080/api/aircraft")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
