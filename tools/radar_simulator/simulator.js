const canvas = document.getElementById('radarCanvas');
const ctx = canvas.getContext('2d');
const renderScale = 3;
ctx.scale(renderScale, renderScale);
const center = 120;
const colors = {
  background: '#040a1c', grid: '#106420', road: '#69737d', primary: '#3c4650',
  city: '#aaaaaa', aircraft: '#ff0000', label: '#ffffff', vector: '#ff00ff'
};
const defaults = {
  range: 25, night: false, nightStart: '22:00', nightEnd: '07:00', animate: false,
  live: true,
  grid: true, roads: true, primary: true, cities: true, runways: true, labels: true, vectors: true,
  latitude: '51.483004', longitude: '7.415811', miles: false, footer: true, weather: true,
  fahrenheit: false, altitudeMetres: true, clock24: true, textScale: 90,
  colors: { ...colors }
};
const locations = {
  dortmund: { latitude: '51.483004', longitude: '7.415811' },
  duesseldorf: { latitude: '51.2895', longitude: '6.7668' },
  frankfurt: { latitude: '50.0379', longitude: '8.5622' }
};
let state = structuredClone(defaults);
let liveAircraft = false;
let lastLiveFetch = 0;
const aircraft = [
  { id: 'DEEXS', callsign: 'DEEXS', route: '', routeOrigin: '', routeDestination: '', x: -2.4, y: 1.8, heading: 34, speed: .020, alt: '71 m', type: 'C172' },
  { id: 'DTM-GDN', callsign: 'DTM-GDN', route: 'DTM-GDN', routeOrigin: 'Dortmund', routeDestination: 'London', x: -8.3, y: 5.4, heading: 350, speed: .012, alt: '2560 m', type: 'A21N' },
  { id: 'FDL.W', callsign: 'FDL.W', route: '', routeOrigin: '', routeDestination: '', x: 8.4, y: 2.0, heading: 270, speed: .018, alt: '11582 m', type: 'B738' },
  { id: 'LPL-TFS', callsign: 'LPL-TFS', route: 'LPL-TFS', routeOrigin: 'Liverpool', routeDestination: 'Tenerife', x: 4.5, y: -2.5, heading: 210, speed: .010, alt: '11582 m', type: 'B738' }
];
const cities = [
  ['DO', 51.5142, 7.4684], ['WIT', 51.4333, 7.3333], ['HA', 51.3671, 7.4633],
  ['BO', 51.4818, 7.2162], ['E', 51.4556, 7.0116], ['WAL', 51.6219, 7.3976],
  ['HER', 51.5369, 7.2009], ['CAS', 51.5567, 7.3116], ['UN', 51.5340, 7.6890],
  ['HAM', 51.6739, 7.8150], ['RE', 51.6141, 7.1979], ['IS', 51.3755, 7.7028],
  ['GE', 51.5177, 7.0857], ['W', 51.2707, 7.1808]
];
const fallbackRoads = [
  { kind: 'motorway', points: [[-20, 10], [-13, 8], [-8, 1], [-2, -2], [4, -3], [13, -12], [20, -18]] },
  { kind: 'motorway', points: [[-18, -16], [-10, -10], [-3, -4], [2, 3], [8, 9], [17, 16]] },
  { kind: 'motorway', points: [[-20, 1], [-11, 1], [-3, 0], [5, 1], [14, 2], [20, 4]] },
  { kind: 'primary', points: [[-16, 20], [-10, 12], [-6, 5], [-5, -2], [-8, -12], [-13, -20]] },
  { kind: 'primary', points: [[-4, 20], [-2, 12], [2, 7], [7, 3], [13, 0], [20, -1]] },
  { kind: 'primary', points: [[-20, -3], [-12, -3], [-5, -5], [0, -9], [4, -17], [8, -21]] }
];
let roads = fallbackRoads;
let mapLoaded = false;
let airportData = [];
let runwayData = [];
let airportDataLoaded = false;

function $(id) { return document.getElementById(id); }
function kmToPx(km) { return 96 * km / state.range; }
function pointToScreen(x, y) { return [center + kmToPx(x), center - kmToPx(y)]; }
function inside(x, y) { return Math.hypot(x - center, y - center) <= 119; }

function clipSegment(a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const ax = a[0] - center, ay = a[1] - center;
  const qa = dx * dx + dy * dy;
  if (!qa) return inside(a[0], a[1]) ? [a, b] : null;
  const qb = 2 * (ax * dx + ay * dy);
  const qc = ax * ax + ay * ay - 119 * 119;
  const disc = qb * qb - 4 * qa * qc;
  let enter = 0, leave = 1;
  if (disc < 0) return qc <= 0 ? [a, b] : null;
  const root = Math.sqrt(disc);
  enter = Math.max(0, Math.min(1, (-qb - root) / (2 * qa), (-qb + root) / (2 * qa)));
  leave = Math.min(1, Math.max(0, (-qb - root) / (2 * qa), (-qb + root) / (2 * qa)));
  if (enter > leave) return null;
  return [[a[0] + dx * enter, a[1] + dy * enter], [a[0] + dx * leave, a[1] + dy * leave]];
}

function drawGrid() {
  if (!state.grid) return;
  ctx.strokeStyle = state.colors.grid; ctx.lineWidth = 1; ctx.setLineDash([3, 5]);
  [24, 48, 72, 96].forEach(r => { ctx.beginPath(); ctx.arc(center, center, r, 0, Math.PI * 2); ctx.stroke(); });
  ctx.setLineDash([]); ctx.beginPath(); ctx.moveTo(1, center); ctx.lineTo(239, center); ctx.moveTo(center, 1); ctx.lineTo(center, 239); ctx.stroke();
}

function drawRoads() {
  roads.forEach(road => {
    if ((road.kind === 'motorway' && !state.roads) || (road.kind === 'primary' && !state.primary)) return;
    ctx.strokeStyle = road.kind === 'motorway' ? state.colors.road : state.colors.primary;
    ctx.lineWidth = road.kind === 'motorway' ? 1.2 : .8; ctx.beginPath();
    for (let i = 1; i < road.points.length; i++) {
      const clipped = clipSegment(pointToScreen(...road.points[i - 1]), pointToScreen(...road.points[i]));
      if (!clipped) continue;
      ctx.moveTo(...clipped[0]); ctx.lineTo(...clipped[1]);
    }
    ctx.stroke();
  });
}

function parseMapHeader(source) {
  const arrays = new Map();
  const arrayPattern = /constexpr\s+MapPoint\s+(kRoad[A-Za-z0-9_]+)\[\]\s*=\s*\{([\s\S]*?)\};/g;
  let match;
  while ((match = arrayPattern.exec(source)) !== null) {
    const points = [];
    const pointPattern = /\{\s*(-?\d+(?:\.\d+)?)f,\s*(-?\d+(?:\.\d+)?)f\s*\}/g;
    let point;
    while ((point = pointPattern.exec(match[2])) !== null) {
      const lat = Number(point[1]);
      const lon = Number(point[2]);
      const lat0 = Number(state.latitude);
      const lon0 = Number(state.longitude);
      points.push([(lon - lon0) * 111.32 * Math.cos(lat0 * Math.PI / 180), (lat - lat0) * 111.32]);
    }
    arrays.set(match[1], points);
  }
  const result = [];
  const roadPattern = /\{"([^\"]+)",\s*(kRoad[A-Za-z0-9_]+),[\s\S]*?MapRoadKind::(kMotorway|kPrimary)\}/g;
  while ((match = roadPattern.exec(source)) !== null) {
    const points = arrays.get(match[2]);
    if (points && points.length > 1) result.push({ name: match[1], kind: match[3] === 'kPrimary' ? 'primary' : 'motorway', points });
  }
  return result;
}

async function loadMap() {
  try {
    const response = await fetch('../../include/ui/motorway_map_30km.h', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const parsed = parseMapHeader(await response.text());
    if (!parsed.length) throw new Error('No roads found');
    roads = parsed; mapLoaded = true; $('statusText').textContent = `Firmware map loaded (${parsed.length} roads)`; render();
  } catch (error) {
    roads = fallbackRoads; mapLoaded = false; $('statusText').textContent = 'Mock map (serve repository root to load firmware map)';
  }
}

async function loadAirportData() {
  try {
    const response = await fetch('../../src/data/large_airports_data.cpp', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const source = await response.text();
    const runwayStart = source.indexOf('const Runway kRunways[]');
    if (runwayStart < 0) throw new Error('Runway data not found');
    const airports = [];
    const airportPattern = /\{"([A-Z0-9]{4})",\s*(-?\d+),\s*(-?\d+)\}/g;
    let match;
    const airportSource = source.slice(0, runwayStart);
    const lat0 = Number(state.latitude), lon0 = Number(state.longitude);
    while ((match = airportPattern.exec(airportSource)) !== null) {
      airports.push({
        ident: match[1],
        x: (Number(match[3]) / 1e7 - lon0) * 111.32 * Math.cos(lat0 * Math.PI / 180),
        y: (Number(match[2]) / 1e7 - lat0) * 111.32
      });
    }
    const runwayList = [];
    const runwayPattern = /\{(\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*\d+\}/g;
    const runwaySource = source.slice(runwayStart);
    while ((match = runwayPattern.exec(runwaySource)) !== null) {
      const airport = airports[Number(match[1])];
      if (!airport) continue;
      const from = [(Number(match[3]) / 1e7 - lon0) * 111.32 * Math.cos(lat0 * Math.PI / 180), (Number(match[2]) / 1e7 - lat0) * 111.32];
      const to = [(Number(match[5]) / 1e7 - lon0) * 111.32 * Math.cos(lat0 * Math.PI / 180), (Number(match[4]) / 1e7 - lat0) * 111.32];
      if (Math.min(Math.hypot(...from), Math.hypot(...to)) <= state.range + 8) runwayList.push([from, to]);
    }
    airportData = airports.filter(airport => Math.hypot(airport.x, airport.y) <= state.range + 8);
    runwayData = runwayList; airportDataLoaded = true; render();
  } catch (error) {
    airportData = []; runwayData = []; airportDataLoaded = false;
  }
}

function drawCities() {
  if (!state.cities) return;
  const accepted = [];
  const lat0 = Number(state.latitude), lon0 = Number(state.longitude);
  const size = 5 * state.textScale / 100;
  ctx.fillStyle = state.colors.city; ctx.font = `${size}px Arial`; ctx.textBaseline = 'middle';
  const protectedAreas = [
    [102, 108, 138, 132], [98, 0, 142, 28], [98, 212, 142, 240],
    [0, 102, 30, 138], [196, 98, 240, 142]
  ];
  const overlaps = (a, b, margin = 0) => a[0] <= b[2] + margin && a[2] + margin >= b[0] && a[1] <= b[3] + margin && a[3] + margin >= b[1];
  cities.forEach(([name, lat, lon]) => {
    const xKm = (lon - lon0) * 111.32 * Math.cos(lat0 * Math.PI / 180);
    const yKm = (lat - lat0) * 111.32;
    const [sx, sy] = pointToScreen(xKm, yKm);
    if (!inside(sx, sy)) return;
    const width = ctx.measureText(name).width;
    const right = sx < center;
    const labelX = right ? sx + 4 : sx - 4;
    const box = right ? [labelX, sy - 3, labelX + width, sy + 3] : [labelX - width, sy - 3, labelX, sy + 3];
    let hidden = protectedAreas.some(area => overlaps(box, area, 2)) || accepted.some(area => overlaps(box, area, 2));
    if (!hidden) hidden = aircraft.some(plane => { const p = pointToScreen(plane.x, plane.y); return inside(...p) && Math.hypot(p[0] - sx, p[1] - sy) < 16; });
    if (hidden) return;
    ctx.beginPath(); ctx.arc(sx, sy, 2, 0, Math.PI * 2); ctx.fill();
    ctx.textAlign = right ? 'left' : 'right'; ctx.fillText(name, labelX, sy);
    accepted.push(box);
  });
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
}

function drawRunways() {
  if (!state.runways) return;
  ctx.strokeStyle = '#3896aa'; ctx.lineWidth = 1;
  const source = airportDataLoaded ? runwayData : [[[-15, -6], [7, 10]], [[-12, 11], [13, 8]]];
  source.forEach(([from, to]) => {
    const clipped = clipSegment(pointToScreen(...from), pointToScreen(...to));
    if (!clipped) return;
    ctx.beginPath(); ctx.moveTo(...clipped[0]); ctx.lineTo(...clipped[1]); ctx.stroke();
  });
  if (state.labels && airportDataLoaded) {
    ctx.fillStyle = '#6ed2e6'; ctx.font = `${5 * state.textScale / 100}px Arial`; ctx.textAlign = 'center';
    airportData.forEach(airport => {
      const p = pointToScreen(airport.x, airport.y);
      if (inside(...p)) ctx.fillText(airport.ident, p[0], p[1] - 3);
    });
    ctx.textAlign = 'left';
  }
}

function drawAircraft() {
  const scale = kmToPx(1);
  aircraft.forEach(plane => {
    const [x, y] = pointToScreen(plane.x, plane.y); if (!inside(x, y)) return;
    const angle = (plane.heading - 90) * Math.PI / 180;
    if (state.vectors) { ctx.strokeStyle = state.colors.vector; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + Math.cos(angle) * 13, y + Math.sin(angle) * 13); ctx.stroke(); }
    ctx.save(); ctx.translate(x, y); ctx.rotate(angle); ctx.fillStyle = state.colors.aircraft; ctx.beginPath(); ctx.moveTo(9, 0); ctx.lineTo(-6, -4); ctx.lineTo(-3, 0); ctx.lineTo(-6, 4); ctx.closePath(); ctx.fill(); ctx.restore();
    if (state.labels) {
      const size = 7 * state.textScale / 100;
      ctx.fillStyle = state.colors.label; ctx.font = `bold ${size}px Arial`; ctx.fillText(plane.id, x + 7, y - 13);
      ctx.fillStyle = '#5ac8ff'; ctx.fillText(plane.type, x + 7, y - 4);
      ctx.fillStyle = '#ffc800'; ctx.fillText(formatAltitude(plane), x + 7, y + 6);
    }
  });
}

function applyLiveAircraft(items) {
  const lat0 = Number(state.latitude), lon0 = Number(state.longitude);
  const next = items.filter(item => Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lon))).map(item => ({
    id: String(item.route || item.flight || item.callsign || item.hex || 'UNKNOWN').trim() || 'UNKNOWN',
    callsign: String(item.flight || item.callsign || item.hex || 'UNKNOWN').trim() || 'UNKNOWN',
    route: String(item.route || '').trim(),
    routeOrigin: String(item.route_origin || '').trim(),
    routeDestination: String(item.route_destination || '').trim(),
    x: (Number(item.lon) - lon0) * 111.32 * Math.cos(lat0 * Math.PI / 180),
    y: (Number(item.lat) - lat0) * 111.32,
    heading: Number(item.track) || 0,
    speed: 0,
    alt: item.alt_baro === 'ground' ? 'GND' : '', altitudeFeet: Number(item.alt_baro),
    type: String(item.route_type || item.t || '')
  }));
  aircraft.splice(0, aircraft.length, ...next);
  liveAircraft = true;
  $('aircraftReadout').textContent = `${aircraft.length} aircraft`;
  $('statusText').textContent = `Live ADS-B (${aircraft.length})`;
}

async function fetchLiveAircraft() {
  if (!state.live || Date.now() - lastLiveFetch < 3000) return;
  lastLiveFetch = Date.now();
  try {
    const query = new URLSearchParams({ lat: state.latitude, lon: state.longitude, range: state.range });
    const response = await fetch(`/api/aircraft?${query}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    applyLiveAircraft(data.aircraft || []);
  } catch (error) {
    liveAircraft = false;
    $('statusText').textContent = 'Live ADS-B unavailable';
  }
}

function formatAltitude(plane) {
  if (plane.alt === 'GND') return 'GND';
  if (Number.isFinite(plane.altitudeFeet)) {
    return state.altitudeMetres ? `${Math.round(plane.altitudeFeet * 0.3048)} m` : `${Math.round(plane.altitudeFeet)} ft`;
  }
  const metres = Number.parseInt(plane.alt, 10);
  if (!Number.isFinite(metres)) return '-';
  if (state.altitudeMetres) return `${metres} m`;
  return `${Math.round(metres / 0.3048)} ft`;
}

function headingLabel(degrees) {
  const value = ((Number(degrees) || 0) + 360) % 360;
  const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  return `${Math.round(value)}° ${directions[Math.round(value / 45) % 8]}`;
}

function aircraftDistanceKm(plane) {
  return Math.hypot(plane.x, plane.y);
}

function updateAircraftTable(night) {
  const body = $('aircraftTableBody');
  const visible = night ? [] : aircraft.filter(plane => inside(...pointToScreen(plane.x, plane.y)))
    .sort((a, b) => aircraftDistanceKm(a) - aircraftDistanceKm(b));
  body.replaceChildren();
  visible.forEach(plane => {
    const row = document.createElement('tr');
    [plane.callsign || plane.id, plane.route || '-', plane.routeOrigin || '-', plane.routeDestination || '-', plane.type || '-', formatAltitude(plane), headingLabel(plane.heading), `${aircraftDistanceKm(plane).toFixed(1)} km`].forEach(value => {
      const cell = document.createElement('td'); cell.textContent = value; row.appendChild(cell);
    });
    body.appendChild(row);
  });
  $('visibleAircraftCount').textContent = `${visible.length} visible`;
  $('emptyAircraftMessage').hidden = visible.length !== 0;
}

function inNightWindow(minutes) {
  if (!state.night) return false;
  const start = toMinutes(state.nightStart), end = toMinutes(state.nightEnd); if (start === end) return true;
  return start < end ? minutes >= start && minutes < end : minutes >= start || minutes < end;
}
function toMinutes(value) { const [h, m] = value.split(':').map(Number); return h * 60 + m; }

function render() {
  ctx.fillStyle = state.colors.background; ctx.fillRect(0, 0, 240, 240);
  const [h, m] = $('simTime').value.split(':').map(Number); const night = inNightWindow(h * 60 + m);
  $('statusText').textContent = night ? 'Night mode' : (state.live && liveAircraft ? `Live ADS-B (${aircraft.length})` : (mapLoaded ? 'Firmware map loaded' : 'Mock map')); $('clockReadout').textContent = $('simTime').value;
  $('aircraftReadout').textContent = `${aircraft.length} aircraft`;
  updateAircraftTable(night);
  if (night) return;
  ctx.save(); ctx.beginPath(); ctx.arc(center, center, 119, 0, Math.PI * 2); ctx.clip();
  drawGrid(); drawRoads(); drawRunways(); drawCities(); drawAircraft(); ctx.restore();
  ctx.strokeStyle = '#000'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(center, center, 119, 0, Math.PI * 2); ctx.stroke();
  ctx.fillStyle = state.colors.label; ctx.font = `bold ${7 * state.textScale / 100}px Arial`; ctx.textAlign = 'center'; ctx.fillText('N', center, 11); ctx.fillText('S', center, 237); ctx.textAlign = 'left'; ctx.fillText('W', 4, center + 2); ctx.fillText('E', 232, center + 2);
  if (state.footer) {
    ctx.fillStyle = state.colors.background; ctx.fillRect(65, 222, 110, 12);
    ctx.fillStyle = state.colors.label; ctx.font = `${5 * state.textScale / 100}px Arial`; ctx.textAlign = 'center';
    const temp = state.fahrenheit ? '65 F' : '18 C';
    const time = state.clock24 ? $('simTime').value : format12Hour($('simTime').value);
    ctx.fillText(state.weather ? `${temp}  CLEAR  ${time}` : time, center, 231);
  }
}

function format12Hour(value) {
  const [hour, minute] = value.split(':').map(Number);
  const suffix = hour >= 12 ? 'PM' : 'AM';
  return `${String(hour % 12 || 12).padStart(2, '0')}:${String(minute).padStart(2, '0')} ${suffix}`;
}

function bindControls() {
  $('rangeSelect').onchange = event => { state.range = Number(event.target.value); $('rangeReadout').textContent = `Range ${state.range} ${state.miles ? 'mi' : 'km'}`; render(); };
  ['animateToggle','nightToggle','gridToggle','roadsToggle','primaryToggle','citiesToggle','runwaysToggle','labelsToggle','vectorsToggle','liveToggle'].forEach(id => $(id).onchange = event => { const key = { animateToggle:'animate', nightToggle:'night', gridToggle:'grid', roadsToggle:'roads', primaryToggle:'primary', citiesToggle:'cities', runwaysToggle:'runways', labelsToggle:'labels', vectorsToggle:'vectors', liveToggle:'live' }[id]; state[key] = event.target.checked; if (key === 'live' && !state.live) { aircraft.splice(0, aircraft.length, ...mockAircraft); liveAircraft = false; } render(); });
  ['nightStart','nightEnd','simTime'].forEach(id => $(id).oninput = render);
  ['milesToggle','footerToggle','weatherToggle','fahrenheitToggle','altitudeToggle','clockToggle','textScale'].forEach(id => $(id).oninput = syncGeneralState);
  $('locationSelect').onchange = event => { const location = locations[event.target.value]; if (!location) return; state.latitude = location.latitude; state.longitude = location.longitude; syncControls(); syncGeneralState(); };
  ['latitude','longitude'].forEach(id => $(id).onchange = syncGeneralState);
  Object.keys(colors).forEach(key => { const id = { background:'colorBackground', grid:'colorGrid', road:'colorRoad', primary:'colorPrimary', city:'colorCity', aircraft:'colorAircraft', label:'colorLabel', vector:'colorVector' }[key]; $(id).oninput = event => { state.colors[key] = event.target.value; render(); }; });
  $('resetButton').onclick = () => { state = structuredClone(defaults); syncControls(); render(); };
}
function syncGeneralState() {
  state.latitude = $('latitude').value; state.longitude = $('longitude').value;
  state.miles = $('milesToggle').checked; state.footer = $('footerToggle').checked; state.weather = $('weatherToggle').checked;
  state.fahrenheit = $('fahrenheitToggle').checked; state.altitudeMetres = $('altitudeToggle').checked; state.clock24 = $('clockToggle').checked;
  state.textScale = Number($('textScale').value); $('textScaleValue').value = `${state.textScale}%`;
  $('rangeReadout').textContent = `Range ${state.range} ${state.miles ? 'mi' : 'km'}`;
  roads = fallbackRoads; mapLoaded = false; airportDataLoaded = false; render(); loadMap(); loadAirportData();
}
function syncControls() { $('rangeSelect').value = state.range; $('rangeReadout').textContent = `Range ${state.range} ${state.miles ? 'mi' : 'km'}`; $('nightToggle').checked = state.night; $('animateToggle').checked = state.animate; $('liveToggle').checked = state.live; ['grid','roads','primary','cities','runways','labels','vectors'].forEach(key => $(key + 'Toggle').checked = state[key]); ['nightStart','nightEnd'].forEach(id => $(id).value = state[id]); $('latitude').value = state.latitude; $('longitude').value = state.longitude; $('locationSelect').value = Object.keys(locations).find(key => locations[key].latitude === state.latitude && locations[key].longitude === state.longitude) || 'dortmund'; $('milesToggle').checked = state.miles; $('footerToggle').checked = state.footer; $('weatherToggle').checked = state.weather; $('fahrenheitToggle').checked = state.fahrenheit; $('altitudeToggle').checked = state.altitudeMetres; $('clockToggle').checked = state.clock24; $('textScale').value = state.textScale; $('textScaleValue').value = `${state.textScale}%`; Object.keys(colors).forEach(key => { const id = { background:'colorBackground', grid:'colorGrid', road:'colorRoad', primary:'colorPrimary', city:'colorCity', aircraft:'colorAircraft', label:'colorLabel', vector:'colorVector' }[key]; $(id).value = state.colors[key]; }); }
const mockAircraft = aircraft.map(item => ({ ...item }));
function animate(timestamp) { if (!animate.last) animate.last = timestamp; const dt = Math.min(40, timestamp - animate.last); animate.last = timestamp; fetchLiveAircraft(); if (state.animate && !state.live && !inNightWindow(toMinutes($('simTime').value))) { aircraft.forEach(p => { const a = p.heading * Math.PI / 180; p.x += Math.sin(a) * p.speed * dt; p.y += Math.cos(a) * p.speed * dt; if (Math.abs(p.x) > 28 || Math.abs(p.y) > 28) { p.x *= -.8; p.y *= -.8; } }); } render(); requestAnimationFrame(animate); }

bindControls(); syncControls(); loadMap(); loadAirportData(); requestAnimationFrame(animate);
