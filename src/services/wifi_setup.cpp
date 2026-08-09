#include "services/wifi_setup.h"

#include <WiFi.h>
#include <WiFiManager.h>

#include <cstdio>

#include <Preferences.h>
#include <esp_system.h>
#include <esp_wifi.h>

#ifdef WM_MDNS
#include <ESPmDNS.h>
#endif

#include "config.h"
#include "hardware/display.h"
#include "services/display_settings.h"
#include "services/ota_update.h"
#include "services/radar_location.h"
#include "ui/radar_range.h"
#include "ui/radar_display.h"
#include "ui/status_screens.h"

portMUX_TYPE s_boot_mux = portMUX_INITIALIZER_UNLOCKED;
volatile bool s_boot_tap_pending = false;
volatile bool s_boot_is_down = false;
volatile unsigned long s_boot_down_ms = 0;
bool s_long_press_handled = false;
bool s_boot_interrupt_attached = false;

void IRAM_ATTR onBootButtonIsr() {
  const bool down = digitalRead(config::kBootPin) == LOW;
  const unsigned long now = millis();
  portENTER_CRITICAL_ISR(&s_boot_mux);
  if (down) {
    s_boot_is_down = true;
    s_boot_down_ms = now;
  } else if (s_boot_is_down) {
    const unsigned long held = now - s_boot_down_ms;
    if (held >= config::kBootTapMinMs && held < config::kBootResetHoldMs) {
      s_boot_tap_pending = true;
    }
    s_boot_is_down = false;
  }
  portEXIT_CRITICAL_ISR(&s_boot_mux);
}

void initBootButton() {
  pinMode(config::kBootPin, INPUT_PULLUP);
  if (s_boot_interrupt_attached) {
    return;
  }
  attachInterrupt(digitalPinToInterrupt(static_cast<uint8_t>(config::kBootPin)),
                  onBootButtonIsr, CHANGE);
  s_boot_interrupt_attached = true;
}

namespace {

constexpr char kPortalGlobalStyle[] =
    "<style>"
    "*{box-sizing:border-box}"
    "body{margin:0;padding:24px;background:#0d151e;color:#d7e0e9;"
    "font-family:Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.45}"
    "body>div,body>form,form{max-width:760px;margin:0 auto}"
    ".wrap{display:block!important;width:100%!important;min-width:0!important;"
    "max-width:760px!important;text-align:left!important}"
    ".wrap form{display:block!important;width:100%!important}"
    ".wrap form>div{float:none!important;clear:both!important;width:100%!important;"
    "display:block!important}"
    "form{padding:24px;background:#141f2a;border:1px solid #2a3a49;"
    "border-radius:12px;box-shadow:0 12px 32px #0005}"
    ".c{float:none!important;clear:both!important;width:100%!important;"
    "box-sizing:border-box!important}"
    "h1,h2,h3{color:#edf3f8;font-weight:600;letter-spacing:.01em}"
    "h1{font-size:1.35rem;margin:0 0 1.2rem}"
    "h2{font-size:1.05rem;margin:1.5rem 0 .6rem}"
    "h3{font-size:1rem;margin:1.5rem 0 .7rem!important;padding:10px 12px;"
    "background:#1a2937;border-left:3px solid #62899d;border-radius:6px}"
    "label{color:#b8c6d3}"
    "input[type=text],input[type=password],input[type=number],select{"
    "width:100%;padding:9px 10px;background:#0f1923;color:#e4edf4;"
    "border:1px solid #35495b;border-radius:6px;outline:none}"
    "input[type=color]{width:52px;height:32px;padding:3px;background:#0f1923;"
    "border:1px solid #526577;border-radius:5px}"
    "input[type=range]{accent-color:#7098aa}input[type=checkbox]{accent-color:#7098aa}"
    "button,input[type=submit]{padding:8px 13px;background:#38596b;color:#eef5f8;"
    "border:1px solid #5e8191;border-radius:6px;font:inherit;cursor:pointer}"
    "button:hover,input[type=submit]:hover{background:#486f80;border-color:#83a8b7}"
    "a{color:#8eb5c5}small{color:#9aaabd}"
    ".home-link{display:inline-block;margin:0 0 16px;padding:8px 13px;"
    "background:#38596b;color:#eef5f8;border:1px solid #5e8191;"
    "border-radius:6px;text-decoration:none;font-weight:600}"
    ".home-link:hover{background:#486f80;border-color:#83a8b7}"
    "@media(max-width:520px){body{padding:12px}form{padding:16px}}"
    "</style>"
    "<script>document.addEventListener('DOMContentLoaded',function(){"
    "var w=document.querySelector('.wrap');if(!w)return;"
    "if(location.pathname==='/' ){"
    "var d=document.createElement('a');d.href='/display';d.textContent='Display';"
    "d.className='home-link';w.prepend(d);return;}"
    "var a=document.createElement('a');a.href='/';a.textContent='Home';"
    "a.className='home-link';w.prepend(a);"
    "});</script>";

/** Separate from planeradar prefs (rangeInit) to avoid NVS handle conflicts. */
constexpr char kWifiPrefsNamespace[] = "wifi";
constexpr char kPrefsForcePortalKey[] = "portal";

bool s_force_config_portal = false;
WiFiManager s_wm;
bool s_wm_configured = false;

void ensureWifiManager();
void startLanWebPortal();
void stopLanWebPortal();
bool wifiLinkUp();
void attachSettingsRoutes();

void handleDisplayPage() {
  if (!s_wm.server) {
    return;
  }
  s_wm.server->send(200, "text/html",
                    "<!doctype html><html><head><meta name='viewport' "
                    "content='width=device-width,initial-scale=1'>"
                    "<title>Plane Radar Display</title><style>"
                    "body{margin:0;padding:20px;background:#0d151e;color:#d7e0e9;"
                    "font-family:Segoe UI,Arial,sans-serif;text-align:center}"
                    "main{max-width:520px;margin:auto;background:#141f2a;"
                    "padding:20px;border:1px solid #2a3a49;border-radius:12px}"
                    "img{width:min(100%,480px);height:auto;image-rendering:auto;"
                    "border:1px solid #526577;border-radius:8px}"
                    "a{display:inline-block;margin-top:16px;padding:8px 13px;"
                    "background:#38596b;color:#eef5f8;border:1px solid #5e8191;"
                    "border-radius:6px;text-decoration:none}</style></head><body>"
                    "<main><h2>Plane Radar Display</h2>"
                    "<img id='display' src='/display.bmp'>"
                    "<script>setInterval(function(){document.getElementById('display').src="
                    "'/display.bmp?t='+Date.now()},5000);</script>"
                    "<br><a href='/'>Home</a></main></body></html>");
}

void handleDisplayBmp() {
  if (!s_wm.server) {
    return;
  }
  constexpr size_t kBmpSize = 54 + 240 * 240 * 3;
  s_wm.server->setContentLength(kBmpSize);
  s_wm.server->send(200, "image/bmp", "");
  WiFiClient client = s_wm.server->client();
  ui::radarDisplayWriteBmp(client);
}

constexpr int kCoordParamLen = 20;
constexpr char kLatitudeInputAttrs[] =
    "type=\"number\" step=\"0.000001\" min=\"-90\" max=\"90\"";
constexpr char kLongitudeInputAttrs[] =
    "type=\"number\" step=\"0.000001\" min=\"-180\" max=\"180\"";
constexpr int kOtaPasswordParamLen =
    static_cast<int>(services::settings::kOtaPasswordMaxLen);
constexpr int kTextScaleParamLen = 4;

WiFiManagerParameter s_param_lat("radar_lat", "Latitude (deg)", "0",
                                kCoordParamLen, kLatitudeInputAttrs);
WiFiManagerParameter s_param_lon("radar_lon", "Longitude (deg)", "0",
                                kCoordParamLen, kLongitudeInputAttrs);
char s_miles_checkbox_attrs[32] = "type=\"checkbox\"";
WiFiManagerParameter s_param_miles("use_miles", "Display distances in miles", "T", 2,
                                   s_miles_checkbox_attrs, WFM_LABEL_AFTER);

char s_runways_checkbox_attrs[32] = "type=\"checkbox\"";
WiFiManagerParameter s_param_runways("show_runways", "Show airport runways", "T", 2,
                                     s_runways_checkbox_attrs, WFM_LABEL_AFTER);
constexpr char kRangeInputAttrs[] =
    "type=\"range\" min=\"0\" max=\"3\" step=\"1\" "
    "title=\"5 km / 10 km / 15 km / 25 km\" "
    "oninput=\"document.getElementById('range_value').value="
    "['5 km','10 km','15 km','25 km'][this.value]\"";
WiFiManagerParameter s_param_range(
    "range_index", "Radar range (5 / 10 / 15 / 25 km)", "1", 2,
    kRangeInputAttrs);
WiFiManagerParameter s_param_range_break("<br/>");
WiFiManagerParameter s_param_range_output(
    "<div style=\"text-align:center;margin-top:-5px\">"
    "<output id=\"range_value\">10 km</output></div>"
    "<script>(function(){var s=document.getElementById('range_index'),"
    "o=document.getElementById('range_value'),v=['5 km','10 km','15 km','25 km'];"
    "if(s&&o)o.value=v[s.value]||'10 km';})();</script>");

char s_footer_checkbox_attrs[32] = "type=\"checkbox\"";
WiFiManagerParameter s_param_footer("show_footer", "Show weather and clock", "T",
                                    2, s_footer_checkbox_attrs,
                                    WFM_LABEL_AFTER);

char s_weather_checkbox_attrs[32] = "type=\"checkbox\"";
WiFiManagerParameter s_param_weather(
    "show_weather", "Show current weather", "T", 2,
    s_weather_checkbox_attrs, WFM_LABEL_AFTER);

char s_fahrenheit_checkbox_attrs[32] = "type=\"checkbox\"";
WiFiManagerParameter s_param_fahrenheit(
    "temp_f", "Temperature in Fahrenheit", "T", 2,
    s_fahrenheit_checkbox_attrs, WFM_LABEL_AFTER);

char s_altitude_metres_checkbox_attrs[32] = "type=\"checkbox\"";
WiFiManagerParameter s_param_altitude_metres(
    "alt_m", "Display altitude in metres", "T", 2,
    s_altitude_metres_checkbox_attrs, WFM_LABEL_AFTER);

char s_clock24_checkbox_attrs[32] = "type=\"checkbox\"";
WiFiManagerParameter s_param_clock24("clock_24", "Use 24-hour clock", "T", 2,
                                     s_clock24_checkbox_attrs,
                                     WFM_LABEL_AFTER);

WiFiManagerParameter s_param_after_clock_break("<br/>");

constexpr char kTextScaleAttrs[] =
    "type=\"range\" min=\"80\" max=\"130\" step=\"5\" "
    "oninput=\"document.getElementById('text_scale_value').value="
    "this.value+'%'\"";
WiFiManagerParameter s_param_text_scale(
    "text_scale", "Radar text size", "120", kTextScaleParamLen,
    kTextScaleAttrs);
WiFiManagerParameter s_param_text_scale_output(
    "<div style=\"text-align:center;margin-top:-5px\">"
    "<output id=\"text_scale_value\" for=\"text_scale\"></output></div>"
    "<script>(function(){var s=document.getElementById('text_scale'),"
    "o=document.getElementById('text_scale_value');"
      "if(s&&o)o.value=s.value+'%';})();</script>");
char s_night_checkbox_attrs[32] = "type=\"checkbox\"";
WiFiManagerParameter s_param_night_enabled(
    "night_enabled", "Enable night mode", "T", 2,
    s_night_checkbox_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_night_break("<br/>");
constexpr char kNightTimeAttrs[] = "type=\"time\"";
WiFiManagerParameter s_param_night_start(
    "night_start", "Night mode start", "22:00", 6, kNightTimeAttrs);
WiFiManagerParameter s_param_night_end(
    "night_end", "Night mode end", "07:00", 6, kNightTimeAttrs);

constexpr char kColorInputAttrs[] = "type=\"color\"";
constexpr int kColorInputLen = 8;
WiFiManagerParameter s_param_color_background("color_bg", "Background", "#040a1c",
                                               kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_grid("color_grid", "Grid", "#106420",
                                         kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_label("color_label", "Labels", "#ffffff",
                                          kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_center("color_center", "Center marker", "#ffffff",
                                           kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_aircraft("color_aircraft", "Aircraft", "#ff0000",
                                              kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_track("color_track", "Track vector", "#ff00ff",
                                          kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_tag_type("color_tag_type", "Aircraft type", "#ffc800",
                                              kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_tag_alt("color_tag_alt", "Altitude", "#5ac8ff",
                                            kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_runway("color_runway", "Runways", "#3896aa",
                                            kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_runway_label("color_runway_label", "Runway labels", "#6ed2e6",
                                                   kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_footer("color_footer", "Footer background", "#031020",
                                           kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_road("color_road", "Motorways", "#69737d",
                                          kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_road_primary("color_road_primary", "Primary roads", "#3c4650",
                                                 kColorInputLen, kColorInputAttrs);
WiFiManagerParameter s_param_color_city("color_city", "Cities", "#aaaaaa",
                                         kColorInputLen, kColorInputAttrs);

char s_show_grid_attrs[32] = "type=\"checkbox\"";
char s_show_center_attrs[32] = "type=\"checkbox\"";
char s_show_label_attrs[32] = "type=\"checkbox\"";
char s_show_aircraft_attrs[32] = "type=\"checkbox\"";
char s_show_track_attrs[32] = "type=\"checkbox\"";
char s_show_tag_type_attrs[32] = "type=\"checkbox\"";
char s_show_tag_alt_attrs[32] = "type=\"checkbox\"";
char s_show_runway_attrs[32] = "type=\"checkbox\"";
char s_show_runway_label_attrs[32] = "type=\"checkbox\"";
char s_show_road_attrs[32] = "type=\"checkbox\"";
char s_show_road_primary_attrs[32] = "type=\"checkbox\"";
char s_show_city_attrs[32] = "type=\"checkbox\"";
WiFiManagerParameter s_param_show_grid("show_grid", "Show grid", "T", 2,
                                        s_show_grid_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_show_center("show_center", "Show center", "T", 2,
                                          s_show_center_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_show_label("show_label", "Show labels", "T", 2,
                                         s_show_label_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_show_aircraft("show_aircraft", "Show aircraft", "T", 2,
                                            s_show_aircraft_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_show_track("show_track", "Show track vector", "T", 2,
                                         s_show_track_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_show_tag_type("show_tag_type", "Show aircraft type", "T", 2,
                                            s_show_tag_type_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_show_tag_alt("show_tag_alt", "Show altitude", "T", 2,
                                           s_show_tag_alt_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_show_runway("show_runway", "Show runways", "T", 2,
                                          s_show_runway_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_show_runway_label("show_runway_label", "Show runway labels", "T", 2,
                                                s_show_runway_label_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_show_road("show_road", "Show roads", "T", 2,
                                        s_show_road_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_show_road_primary(
    "show_road_primary", "Show primary roads", "T", 2,
    s_show_road_primary_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_show_city("show_city", "Show cities", "T", 2,
                                        s_show_city_attrs, WFM_LABEL_AFTER);
WiFiManagerParameter s_param_color_group_background(
    "<h3 style='margin:1.2rem 0 .4rem'>Hintergrundkarte</h3>");
WiFiManagerParameter s_param_color_group_grid(
    "<h3 style='margin:1.2rem 0 .4rem'>Raster</h3>");
WiFiManagerParameter s_param_color_group_aircraft(
    "<h3 style='margin:1.2rem 0 .4rem'>Flugzeuge</h3>");
WiFiManagerParameter s_param_color_group_general(
    "<h3 style='margin:1.2rem 0 .4rem'>Allgemein</h3>");
WiFiManagerParameter s_param_color_reset_controls(
    "<script>(function(){"
    "var style=document.createElement('style');"
    "style.textContent=\""
    "*{box-sizing:border-box;}"
    "body{margin:0;padding:24px;background:#0d151e;color:#d7e0e9;"
    "font-family:Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.45;}"
    "body>div,body>form,form{max-width:760px;margin:0 auto;}"
    "form{padding:24px;background:#141f2a;border:1px solid #2a3a49;"
    "border-radius:12px;box-shadow:0 12px 32px #0005;}"
    "h1,h2,h3{color:#edf3f8;font-weight:600;letter-spacing:.01em;}"
    "h1{font-size:1.35rem;margin:0 0 1.2rem;}"
    "h2{font-size:1.05rem;margin:1.5rem 0 .6rem;}"
    ".c{float:none!important;clear:both!important;width:100%!important;}"
    "h3{clear:both!important;width:100%!important;font-size:1rem;"
    "margin:1.5rem 0 .7rem!important;padding:10px 12px;"
    "background:#1a2937;border-left:3px solid #62899d;border-radius:6px;}"
    "label{color:#b8c6d3;}"
    "input[type=text],input[type=password],input[type=number],select{"
    "width:100%;padding:9px 10px;background:#0f1923;color:#e4edf4;"
    "border:1px solid #35495b;border-radius:6px;outline:none;}"
    "input[type=text]:focus,input[type=password]:focus,input[type=number]:focus{"
    "border-color:#7098aa;box-shadow:0 0 0 2px #7098aa33;}"
    "input[type=color]{width:52px;height:32px;padding:3px;"
    "background:#0f1923;border:1px solid #526577;border-radius:5px;}"
    "input[type=range]{accent-color:#7098aa;}"
    "input[type=checkbox]{accent-color:#7098aa;}"
    "button,input[type=submit]{padding:8px 13px;background:#38596b;"
    "color:#eef5f8;border:1px solid #5e8191;border-radius:6px;"
    "font:inherit;cursor:pointer;transition:background .15s,border-color .15s;}"
    "button:hover,input[type=submit]:hover{background:#486f80;border-color:#83a8b7;}"
    ".color-controls{min-width:170px;}"
    "@media(max-width:520px){body{padding:12px;}form{padding:16px;}"
    ".color-controls{min-width:145px;}}"
    "a{color:#8eb5c5;}"
    "small{color:#9aaabd;}"
    "\";"
    "document.head.appendChild(style);"
    "document.querySelectorAll('.wrap,.wrap form,.wrap form>div').forEach(function(e){"
    "e.style.setProperty('float','none','important');"
    "e.style.setProperty('clear','both','important');"
    "e.style.setProperty('width','100%','important');"
    "e.style.setProperty('display','block','important');});"
    "var d={color_bg:'#040a1c',color_grid:'#106420',"
    "color_label:'#ffffff',color_center:'#ffffff',"
    "color_aircraft:'#ff0000',color_track:'#ff00ff',"
    "color_tag_type:'#ffc800',color_tag_alt:'#5ac8ff',"
    "color_runway:'#3896aa',color_runway_label:'#6ed2e6',"
    "color_footer:'#031020',color_road:'#69737d',"
    "color_road_primary:'#3c4650',color_city:'#aaaaaa'};"
    "var v={color_grid:'show_grid',color_center:'show_center',"
    "color_label:'show_label',color_aircraft:'show_aircraft',"
    "color_track:'show_track',color_tag_type:'show_tag_type',"
    "color_tag_alt:'show_tag_alt',color_runway:'show_runway',"
    "color_runway_label:'show_runway_label',color_road:'show_road',"
    "color_road_primary:'show_road_primary',color_city:'show_city'};"
    "Object.keys(d).forEach(function(id){"
    "var i=document.getElementById(id);if(!i)return;"
    "var p=i.parentNode;"
    "var r=p.parentNode;"
    "[p,r].forEach(function(e){e.style.setProperty('float','none','important');"
    "e.style.setProperty('clear','both','important');"
    "e.style.setProperty('width','100%','important');"
    "e.style.setProperty('box-sizing','border-box','important');});"
    "var c=document.createElement('span');"
    "c.className='color-controls';"
    "c.style.display='grid';c.style.gridTemplateColumns='4rem auto auto';"
    "c.style.alignItems='center';c.style.gap='8px';"
    "var b=document.createElement('button');b.type='button';"
    "b.textContent='Standard';b.style.margin='0';"
    "b.onclick=function(){i.value=d[id];};"
    "i.style.display='block';i.style.margin='0';"
    "p.replaceChild(c,i);c.appendChild(i);c.appendChild(b);"
    "var x=document.getElementById(v[id]);"
    "if(x){var xp=x.parentNode;xp.style.display='none';"
    "var xl=document.querySelector('label[for=\"'+v[id]+'\"]');"
    "if(xl)xl.style.display='none';"
    "var q=document.createElement('label');q.style.whiteSpace='nowrap';"
    "x.style.display='inline-block';x.title='Anzeigen';q.appendChild(x);"
    "q.appendChild(document.createTextNode(' Anzeigen'));c.appendChild(q);}"
    "p.style.display='grid';p.style.gridTemplateColumns='minmax(9rem,1fr) auto';"
    "p.style.alignItems='center';p.style.gap='8px';"
    "});"
    "document.querySelectorAll('h3').forEach(function(h){"
    "var q=h.parentNode;q.style.setProperty('float','none','important');"
    "q.style.setProperty('clear','both','important');"
    "q.style.setProperty('width','100%','important');});"
    "})();</script>");

constexpr char kOtaPasswordAttrs[] =
    "type=\"password\" autocomplete=\"new-password\" "
    "placeholder=\"leave blank to keep current\"";
WiFiManagerParameter s_param_ota_password(
    "ota_password", "OTA password (user: admin)", "", kOtaPasswordParamLen,
    kOtaPasswordAttrs);

void refreshCheckboxAttrs(char* attrs, size_t attrs_len, bool checked) {
  snprintf(attrs, attrs_len, "type=\"checkbox\"%s",
           checked ? " checked" : "");
}

void refreshPortalParamDefaults() {
  char lat_buf[kCoordParamLen + 1];
  char lon_buf[kCoordParamLen + 1];
  snprintf(lat_buf, sizeof(lat_buf), "%.6f", services::location::lat());
  snprintf(lon_buf, sizeof(lon_buf), "%.6f", services::location::lon());
  s_param_lat.setValue(lat_buf, kCoordParamLen);
  s_param_lon.setValue(lon_buf, kCoordParamLen);
  refreshCheckboxAttrs(s_miles_checkbox_attrs,
                       sizeof(s_miles_checkbox_attrs),
                       ui::radar::useMiles());
  s_param_miles.setValue("T", 2);
  refreshCheckboxAttrs(s_runways_checkbox_attrs,
                       sizeof(s_runways_checkbox_attrs),
                       ui::radar::showRunways());
  s_param_runways.setValue("T", 2);
  char range_buf[3];
  snprintf(range_buf, sizeof(range_buf), "%u",
           static_cast<unsigned>(ui::radar::rangeIndex()));
  s_param_range.setValue(range_buf, 2);
  refreshCheckboxAttrs(s_footer_checkbox_attrs,
                       sizeof(s_footer_checkbox_attrs),
                       services::settings::footerEnabled());
  s_param_footer.setValue("T", 2);
  refreshCheckboxAttrs(s_weather_checkbox_attrs,
                       sizeof(s_weather_checkbox_attrs),
                       services::settings::weatherEnabled());
  s_param_weather.setValue("T", 2);
  refreshCheckboxAttrs(s_fahrenheit_checkbox_attrs,
                       sizeof(s_fahrenheit_checkbox_attrs),
                       services::settings::temperatureFahrenheit());
  s_param_fahrenheit.setValue("T", 2);
  refreshCheckboxAttrs(s_altitude_metres_checkbox_attrs,
                     sizeof(s_altitude_metres_checkbox_attrs),
                     services::settings::altitudeMetres());
  s_param_altitude_metres.setValue("T", 2);
  refreshCheckboxAttrs(s_clock24_checkbox_attrs,
                       sizeof(s_clock24_checkbox_attrs),
                       services::settings::use24HourClock());
  s_param_clock24.setValue("T", 2);
  char text_scale_buf[kTextScaleParamLen + 1];
  snprintf(text_scale_buf, sizeof(text_scale_buf), "%d",
           services::settings::textScalePercent());
  s_param_text_scale.setValue(text_scale_buf, kTextScaleParamLen);
  refreshCheckboxAttrs(s_night_checkbox_attrs, sizeof(s_night_checkbox_attrs),
                       services::settings::nightModeEnabled());
  s_param_night_enabled.setValue("T", 2);
  char night_start_buf[6];
  char night_end_buf[6];
  snprintf(night_start_buf, sizeof(night_start_buf), "%02u:%02u",
           services::settings::nightStartMinute() / 60,
           services::settings::nightStartMinute() % 60);
  snprintf(night_end_buf, sizeof(night_end_buf), "%02u:%02u",
           services::settings::nightEndMinute() / 60,
           services::settings::nightEndMinute() % 60);
  s_param_night_start.setValue(night_start_buf, 6);
  s_param_night_end.setValue(night_end_buf, 6);
  s_param_ota_password.setValue("", kOtaPasswordParamLen);

  const auto setColor = [](WiFiManagerParameter& param,
                           services::settings::ColorId id) {
    char value[8];
    snprintf(value, sizeof(value), "#%06lX",
             static_cast<unsigned long>(services::settings::color(id)));
    for (char* p = value + 1; *p != '\0'; ++p) {
      if (*p >= 'A' && *p <= 'F') {
        *p = static_cast<char>(*p - 'A' + 'a');
      }
    }
    param.setValue(value, kColorInputLen);
  };
  setColor(s_param_color_background, services::settings::ColorId::kBackground);
  setColor(s_param_color_grid, services::settings::ColorId::kGrid);
  setColor(s_param_color_label, services::settings::ColorId::kLabel);
  setColor(s_param_color_center, services::settings::ColorId::kCenter);
  setColor(s_param_color_aircraft, services::settings::ColorId::kAircraft);
  setColor(s_param_color_track, services::settings::ColorId::kTrackVector);
  setColor(s_param_color_tag_type, services::settings::ColorId::kTagType);
  setColor(s_param_color_tag_alt, services::settings::ColorId::kTagAltitude);
  setColor(s_param_color_runway, services::settings::ColorId::kRunway);
  setColor(s_param_color_runway_label, services::settings::ColorId::kRunwayLabel);
  setColor(s_param_color_footer, services::settings::ColorId::kFooterBackground);
  setColor(s_param_color_road, services::settings::ColorId::kRoad);
  setColor(s_param_color_road_primary,
           services::settings::ColorId::kRoadPrimary);
  setColor(s_param_color_city, services::settings::ColorId::kCity);

  const auto setVisibility = [](char* attrs, size_t attrs_len,
                                WiFiManagerParameter& param,
                                services::settings::VisibilityId id) {
    refreshCheckboxAttrs(attrs, attrs_len,
                         services::settings::visible(id));
    param.setValue("T", 2);
  };
  setVisibility(s_show_grid_attrs, sizeof(s_show_grid_attrs), s_param_show_grid,
                services::settings::VisibilityId::kGrid);
  setVisibility(s_show_center_attrs, sizeof(s_show_center_attrs), s_param_show_center,
                services::settings::VisibilityId::kCenter);
  setVisibility(s_show_label_attrs, sizeof(s_show_label_attrs), s_param_show_label,
                services::settings::VisibilityId::kLabel);
  setVisibility(s_show_aircraft_attrs, sizeof(s_show_aircraft_attrs), s_param_show_aircraft,
                services::settings::VisibilityId::kAircraft);
  setVisibility(s_show_track_attrs, sizeof(s_show_track_attrs), s_param_show_track,
                services::settings::VisibilityId::kTrackVector);
  setVisibility(s_show_tag_type_attrs, sizeof(s_show_tag_type_attrs), s_param_show_tag_type,
                services::settings::VisibilityId::kTagType);
  setVisibility(s_show_tag_alt_attrs, sizeof(s_show_tag_alt_attrs), s_param_show_tag_alt,
                services::settings::VisibilityId::kTagAltitude);
  setVisibility(s_show_runway_attrs, sizeof(s_show_runway_attrs), s_param_show_runway,
                services::settings::VisibilityId::kRunway);
  setVisibility(s_show_runway_label_attrs, sizeof(s_show_runway_label_attrs),
                s_param_show_runway_label,
                services::settings::VisibilityId::kRunwayLabel);
  setVisibility(s_show_road_attrs, sizeof(s_show_road_attrs), s_param_show_road,
                services::settings::VisibilityId::kRoad);
  setVisibility(s_show_road_primary_attrs, sizeof(s_show_road_primary_attrs),
                s_param_show_road_primary,
                services::settings::VisibilityId::kRoadPrimary);
  setVisibility(s_show_city_attrs, sizeof(s_show_city_attrs), s_param_show_city,
                services::settings::VisibilityId::kCity);
}

void onPortalParamsSaved() {
  if (!services::location::saveFromStrings(s_param_lat.getValue(),
                                           s_param_lon.getValue())) {
    Serial.println("Invalid lat/lon in portal — keeping previous location");
  }
  ui::radar::saveMilesFromPortal(s_param_miles.getValue());
  ui::radar::saveRunwaysFromPortal(s_param_runways.getValue());
  ui::radar::saveRangeFromPortal(s_param_range.getValue());
  services::settings::saveFromPortal(
    s_param_footer.getValue(), s_param_weather.getValue(),
    s_param_fahrenheit.getValue(),
    s_param_altitude_metres.getValue(),
    s_param_clock24.getValue(),
    s_param_text_scale.getValue(),
    s_param_ota_password.getValue(),
    s_param_night_enabled.getValue(),
    s_param_night_start.getValue(), s_param_night_end.getValue());
  services::settings::saveColorsFromPortal(
      s_param_color_background.getValue(), s_param_color_grid.getValue(),
      s_param_color_label.getValue(), s_param_color_center.getValue(),
      s_param_color_aircraft.getValue(), s_param_color_track.getValue(),
      s_param_color_tag_type.getValue(), s_param_color_tag_alt.getValue(),
      s_param_color_runway.getValue(), s_param_color_runway_label.getValue(),
      s_param_color_footer.getValue(), s_param_color_road.getValue(),
      s_param_color_city.getValue(), s_param_color_road_primary.getValue());
  services::settings::saveVisibilityFromPortal(
      s_param_show_grid.getValue(), s_param_show_center.getValue(),
      s_param_show_label.getValue(), s_param_show_aircraft.getValue(),
      s_param_show_track.getValue(), s_param_show_tag_type.getValue(),
      s_param_show_tag_alt.getValue(), s_param_show_runway.getValue(),
      s_param_show_runway_label.getValue(), s_param_show_road.getValue(),
      s_param_show_city.getValue(), s_param_show_road_primary.getValue());
}

void savePortalParamsFromRequest(WebServer& web) {
  const String latitude = web.arg("radar_lat");
  const String longitude = web.arg("radar_lon");
  const String miles = web.arg("use_miles");
  const String runways = web.arg("show_runways");
  const String range_index = web.arg("range_index");
  const String footer = web.arg("show_footer");
  const String weather = web.arg("show_weather");
  const String fahrenheit = web.arg("temp_f");
  const String altitude_metres = web.arg("alt_m");
  const String clock24 = web.arg("clock_24");
  const String text_scale = web.arg("text_scale");
  const String ota_password = web.arg("ota_password");
  const String night_enabled = web.arg("night_enabled");
  const String night_start = web.arg("night_start");
  const String night_end = web.arg("night_end");
  const String color_background = web.arg("color_bg");
  const String color_grid = web.arg("color_grid");
  const String color_label = web.arg("color_label");
  const String color_center = web.arg("color_center");
  const String color_aircraft = web.arg("color_aircraft");
  const String color_track = web.arg("color_track");
  const String color_tag_type = web.arg("color_tag_type");
  const String color_tag_alt = web.arg("color_tag_alt");
  const String color_runway = web.arg("color_runway");
  const String color_runway_label = web.arg("color_runway_label");
  const String color_footer = web.arg("color_footer");
  const String color_road = web.arg("color_road");
  const String color_road_primary = web.arg("color_road_primary");
  const String color_city = web.arg("color_city");
  const String show_grid = web.arg("show_grid");
  const String show_center = web.arg("show_center");
  const String show_label = web.arg("show_label");
  const String show_aircraft = web.arg("show_aircraft");
  const String show_track = web.arg("show_track");
  const String show_tag_type = web.arg("show_tag_type");
  const String show_tag_alt = web.arg("show_tag_alt");
  const String show_runway = web.arg("show_runway");
  const String show_runway_label = web.arg("show_runway_label");
  const String show_road = web.arg("show_road");
  const String show_road_primary = web.arg("show_road_primary");
  const String show_city = web.arg("show_city");

  if (!services::location::saveFromStrings(latitude.c_str(),
                                           longitude.c_str())) {
    Serial.println("Invalid lat/lon in portal — keeping previous location");
  }
  ui::radar::saveMilesFromPortal(miles.c_str());
  ui::radar::saveRunwaysFromPortal(runways.c_str());
  ui::radar::saveRangeFromPortal(range_index.c_str());
  services::settings::saveFromPortal(
    footer.c_str(), weather.c_str(), fahrenheit.c_str(),
    altitude_metres.c_str(), clock24.c_str(),
    text_scale.c_str(), ota_password.c_str(),
    night_enabled.c_str(), night_start.c_str(), night_end.c_str());
  services::settings::saveColorsFromPortal(
      color_background.c_str(), color_grid.c_str(), color_label.c_str(),
      color_center.c_str(), color_aircraft.c_str(), color_track.c_str(),
      color_tag_type.c_str(), color_tag_alt.c_str(), color_runway.c_str(),
      color_runway_label.c_str(), color_footer.c_str(), color_road.c_str(),
      color_city.c_str(), color_road_primary.c_str());
  services::settings::saveVisibilityFromPortal(
      show_grid.c_str(), show_center.c_str(), show_label.c_str(),
      show_aircraft.c_str(), show_track.c_str(), show_tag_type.c_str(),
      show_tag_alt.c_str(), show_runway.c_str(), show_runway_label.c_str(),
      show_road.c_str(), show_city.c_str(), show_road_primary.c_str());
  refreshPortalParamDefaults();
}

void handleSettingsSaved() {
  if (!s_wm.server) {
    return;
  }

  WebServer& web = *s_wm.server;
  savePortalParamsFromRequest(web);
  web.send(
      200, "text/html",
      "<!doctype html><html lang='en'><head>"
      "<meta charset='utf-8'>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<meta http-equiv='refresh' content='3;url=/param'>"
      "<title>Setup saved</title>"
       "<style>body{font-family:Segoe UI,Arial,sans-serif;text-align:center;"
       "background:#0d151e;color:#d7e0e9;margin:0;padding:3rem}"
       ".msg{display:inline-block;min-width:16rem;text-align:left;padding:1.5rem;"
       "background:#141f2a;border:1px solid #2a3a49;border-left:4px solid #62899d;"
       "border-radius:12px;box-shadow:0 12px 32px #0005}a{color:#8eb5c5}"
       ".home-link{display:inline-block;margin:0 0 16px;padding:8px 13px;"
       "background:#38596b;color:#eef5f8;border:1px solid #5e8191;"
       "border-radius:6px;text-decoration:none;font-weight:600}</style></head><body>"
       "<div class='msg'><strong>Saved</strong><br>"
       "<small>Returning to Setup in 3 seconds...</small><br><br>"
       "<a class='home-link' href='/'>Home</a></div></body></html>");
}

void attachSettingsRoutes() {
  if (!s_wm.server) {
    return;
  }
  // Browsers request this automatically when opening the portal. Returning
  // an empty response avoids a misleading "handler not found" log entry.
  s_wm.server->on("/favicon.ico", HTTP_GET, []() {
    s_wm.server->send(204, "text/plain", "");
  });
  s_wm.server->on("/display", HTTP_GET, handleDisplayPage);
  s_wm.server->on("/display.bmp", HTTP_GET, handleDisplayBmp);
  // Register before WiFiManager's built-in /paramsave handler so the custom
  // confirmation can redirect back to Setup.
  s_wm.server->on("/paramsave", HTTP_POST, handleSettingsSaved);
}

void attachPortalParams(WiFiManager& wm) {
  refreshPortalParamDefaults();
  wm.addParameter(&s_param_lat);
  wm.addParameter(&s_param_lon);
  wm.addParameter(&s_param_miles);
  wm.addParameter(&s_param_runways);
  wm.addParameter(&s_param_range_break);
  wm.addParameter(&s_param_range);
  wm.addParameter(&s_param_range_output);
  wm.addParameter(&s_param_footer);
  wm.addParameter(&s_param_weather);
  wm.addParameter(&s_param_fahrenheit);
  wm.addParameter(&s_param_altitude_metres);
  wm.addParameter(&s_param_clock24);
  wm.addParameter(&s_param_after_clock_break);
  wm.addParameter(&s_param_text_scale);
  wm.addParameter(&s_param_text_scale_output);
  wm.addParameter(&s_param_night_enabled);
  wm.addParameter(&s_param_night_break);
  wm.addParameter(&s_param_night_start);
  wm.addParameter(&s_param_night_end);
  wm.addParameter(&s_param_ota_password);
  wm.addParameter(&s_param_color_group_general);
  wm.addParameter(&s_param_color_background);
  wm.addParameter(&s_param_color_footer);
  wm.addParameter(&s_param_color_group_background);
  wm.addParameter(&s_param_color_road);
  wm.addParameter(&s_param_show_road);
  wm.addParameter(&s_param_color_road_primary);
  wm.addParameter(&s_param_show_road_primary);
  wm.addParameter(&s_param_color_runway);
  wm.addParameter(&s_param_show_runway);
  wm.addParameter(&s_param_color_runway_label);
  wm.addParameter(&s_param_show_runway_label);
  wm.addParameter(&s_param_color_city);
  wm.addParameter(&s_param_show_city);
  wm.addParameter(&s_param_color_group_grid);
  wm.addParameter(&s_param_color_grid);
  wm.addParameter(&s_param_show_grid);
  wm.addParameter(&s_param_color_center);
  wm.addParameter(&s_param_show_center);
  wm.addParameter(&s_param_color_label);
  wm.addParameter(&s_param_show_label);
  wm.addParameter(&s_param_color_group_aircraft);
  wm.addParameter(&s_param_color_aircraft);
  wm.addParameter(&s_param_show_aircraft);
  wm.addParameter(&s_param_color_track);
  wm.addParameter(&s_param_show_track);
  wm.addParameter(&s_param_color_tag_type);
  wm.addParameter(&s_param_show_tag_type);
  wm.addParameter(&s_param_color_tag_alt);
  wm.addParameter(&s_param_show_tag_alt);
  wm.addParameter(&s_param_color_reset_controls);
  wm.setSaveParamsCallback(onPortalParamsSaved);
}

void markForceConfigPortal() {
  s_force_config_portal = true;
  Preferences prefs;
  if (!prefs.begin(kWifiPrefsNamespace, false)) {
    return;
  }
  prefs.putBool(kPrefsForcePortalKey, true);
  prefs.end();
}

bool consumeForceConfigPortal() {
  if (s_force_config_portal) {
    s_force_config_portal = false;
    Preferences prefs;
    if (prefs.begin(kWifiPrefsNamespace, false)) {
      prefs.remove(kPrefsForcePortalKey);
      prefs.end();
    }
    return true;
  }

  Preferences prefs;
  if (!prefs.begin(kWifiPrefsNamespace, true)) {
    return false;
  }
  const bool pending = prefs.getBool(kPrefsForcePortalKey, false);
  prefs.end();
  if (!pending) {
    return false;
  }

  if (prefs.begin(kWifiPrefsNamespace, false)) {
    prefs.remove(kPrefsForcePortalKey);
    prefs.end();
  }
  return true;
}

bool storedWifiCredentials() {
  wifi_mode_t mode = WIFI_MODE_NULL;
  if (esp_wifi_get_mode(&mode) != ESP_OK || mode == WIFI_MODE_NULL) {
    WiFi.mode(WIFI_STA);
    delay(50);
  }

  wifi_config_t conf = {};
  if (esp_wifi_get_config(WIFI_IF_STA, &conf) != ESP_OK) {
    return false;
  }
  return conf.sta.ssid[0] != '\0';
}

void eraseWifiCredentials() {
  stopLanWebPortal();
  WiFi.setAutoReconnect(false);
  WiFi.mode(WIFI_OFF);
  delay(100);

  ensureWifiManager();
  WiFi.persistent(true);
  s_wm.resetSettings();
  s_wm.erase();
  WiFi.disconnect(true, true);
  WiFi.persistent(false);

  WiFi.mode(WIFI_OFF);
  delay(100);
}

void resetWifiCredentials() {
  markForceConfigPortal();
  eraseWifiCredentials();
  services::location::clear();
  ui::radar::unitsReset();
  services::settings::clear();
  Serial.println("WiFi credentials, location, units, and display settings cleared");
}

void onConfigPortalApStarted(WiFiManager*) {
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
  statusScreenPortal();
#ifdef WM_MDNS
  if (MDNS.begin(config::kPortalHostname)) {
    MDNS.addService("http", "tcp", 80);
    Serial.printf("Setup portal: http://%s.local (or http://%s)\n",
                  config::kPortalHostname, config::kPortalIp);
  } else {
    Serial.printf("Setup portal: http://%s (mDNS unavailable)\n", config::kPortalIp);
  }
#else
  Serial.printf("Setup portal: http://%s\n", config::kPortalIp);
#endif
}

bool wifiLinkUp() {
  return WiFi.status() == WL_CONNECTED &&
         WiFi.localIP() != IPAddress(0, 0, 0, 0);
}

void ensureWifiManager() {
  if (s_wm_configured) {
    return;
  }
  s_wm.setConfigPortalTimeout(config::kWifiPortalTimeoutSec);
  s_wm.setAPStaticIPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1),
                           IPAddress(255, 255, 255, 0));
  s_wm.setHostname(config::kPortalHostname);
  s_wm.setCustomHeadElement(kPortalGlobalStyle);
  s_wm.setTitle("Plane Radar");
  s_wm.setAPCallback(onConfigPortalApStarted);
  attachPortalParams(s_wm);
  services::ota::configure(s_wm, attachSettingsRoutes);
  s_wm_configured = true;
}

void startLanWebPortal() {
  if (!wifiLinkUp() || s_wm.getWebPortalActive() ||
      s_wm.getConfigPortalActive()) {
    return;
  }
  refreshPortalParamDefaults();
  WiFi.mode(WIFI_STA);
  s_wm.setConfigPortalBlocking(false);
#ifdef WM_MDNS
  MDNS.end();
  if (MDNS.begin(config::kPortalHostname)) {
    MDNS.addService("http", "tcp", 80);
  }
#endif
  s_wm.startWebPortal();
  Serial.printf("LAN config: http://%s.local or http://%s\n",
                config::kPortalHostname, WiFi.localIP().toString().c_str());
}

void stopLanWebPortal() {
  if (!s_wm.getWebPortalActive()) {
    return;
  }
  s_wm.stopWebPortal();
#ifdef WM_MDNS
  MDNS.end();
#endif
}

void prepareSta() {
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(WIFI_PS_NONE);
  WiFi.setAutoReconnect(true);
}

void startStaConnect(const String& ssid, const String& pass) {
  prepareSta();
  if (ssid.length() > 0) {
    WiFi.begin(ssid.c_str(), pass.c_str());
  } else {
    WiFi.begin();
  }
}

bool waitForLinkWithUi(const char* ssid_for_ui, unsigned long attempt_ms) {
  const unsigned long deadline = millis() + attempt_ms;
  while (millis() < deadline) {
    if (wifiLinkUp()) {
      return true;
    }
    bootButtonPollLongPress();
    statusScreenConnectingTick();
    delay(config::kWifiConnectingFrameMs);
  }
  return wifiLinkUp();
}

bool tryConnectWithUi(const String& ssid, const String& pass, bool show_ui) {
  if (wifiLinkUp()) {
    return true;
  }

  const char* ui_ssid = ssid.length() > 0 ? ssid.c_str() : "network";
  if (show_ui) {
    statusScreenConnectingBegin(ui_ssid);
  }

  for (uint8_t attempt = 1; attempt <= config::kWifiConnectAttempts; ++attempt) {
    if (attempt > 1) {
      Serial.printf("WiFi connect retry %u/%u\n", attempt,
                    config::kWifiConnectAttempts);
      WiFi.disconnect(true);
      WiFi.mode(WIFI_OFF);
      delay(400);
    }

    startStaConnect(ssid, pass);

    if (waitForLinkWithUi(ui_ssid, config::kWifiConnectAttemptMs)) {
      return true;
    }
  }

  return false;
}

bool connectFallbackNetwork(bool show_ui) {
  const String ssid = config::kWifiFallbackSSID;

  if (ssid.length() == 0) {
    return false;
  }

  Serial.printf("Trying compiled fallback WiFi: %s\n", ssid.c_str());

  return tryConnectWithUi(ssid, config::kWifiFallbackPass, show_ui);
}

bool connectSavedNetwork(bool show_ui) {
  if (!storedWifiCredentials()) {
    return false;
  }

  ensureWifiManager();
  const String ssid = s_wm.getWiFiSSID();
  if (ssid.length() == 0) {
    return false;
  }
  const String pass = s_wm.getWiFiPass();
  return tryConnectWithUi(ssid, pass, show_ui);
}

bool openConfigPortal() {
  stopLanWebPortal();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  delay(50);
  statusScreenPortal();
  s_wm.setConfigPortalBlocking(false);
  s_wm.startConfigPortal(config::kPortalApName);
  while (s_wm.getConfigPortalActive()) {
    bootButtonPollLongPress();
    if (s_wm.process()) {
      return true;
    }
    delay(10);
  }
  return wifiLinkUp();
}

}  // namespace

bool wifiShowsSetupScreenOnBoot() {
  if (s_force_config_portal) {
    return true;
  }
  Preferences prefs;
  if (!prefs.begin(kWifiPrefsNamespace, true)) {
    return false;
  }
  const bool pending = prefs.getBool(kPrefsForcePortalKey, false);
  prefs.end();
  return pending;
}

bool wifiBootButtonPressed() {
  return digitalRead(config::kBootPin) == LOW;
}

void bootButtonInit() { initBootButton(); }

bool bootButtonConsumeTap() {
  portENTER_CRITICAL(&s_boot_mux);
  const bool tap = s_boot_tap_pending;
  if (tap) {
    s_boot_tap_pending = false;
  }
  portEXIT_CRITICAL(&s_boot_mux);
  return tap;
}

void bootButtonPollLongPress() {
  if (wifiBootButtonPressed()) {
    portENTER_CRITICAL(&s_boot_mux);
    if (!s_boot_is_down) {
      s_boot_is_down = true;
      s_boot_down_ms = millis();
    }
    const unsigned long down_ms = s_boot_down_ms;
    portEXIT_CRITICAL(&s_boot_mux);

    if (!s_long_press_handled &&
        millis() - down_ms >= config::kBootResetHoldMs) {
      s_long_press_handled = true;
      Serial.println("BOOT held — resetting WiFi");
      wifiResetCredentialsAndReboot();
    }
  } else {
    portENTER_CRITICAL(&s_boot_mux);
    s_boot_is_down = false;
    portEXIT_CRITICAL(&s_boot_mux);
    s_long_press_handled = false;
  }
}

void wifiResetCredentialsAndReboot() {
  resetWifiCredentials();
  statusScreenWifiReset();
  delay(800);
  esp_restart();
}

bool wifiReconnect() {
  initBootButton();
  Serial.println("WiFi reconnecting...");
  return connectSavedNetwork(true) || connectFallbackNetwork(true);
}

void wifiLoop() {
  ensureWifiManager();
  if (wifiLinkUp()) {
    if (!s_wm.getWebPortalActive() && !s_wm.getConfigPortalActive()) {
      startLanWebPortal();
    }
    if (s_wm.getWebPortalActive() || s_wm.getConfigPortalActive()) {
      bootButtonPollLongPress();
      s_wm.process();
    }
  } else {
    stopLanWebPortal();
  }
}

bool wifiSetupConnect() {
  initBootButton();
  ensureWifiManager();

  const bool force_portal = consumeForceConfigPortal();
  WiFi.setAutoReconnect(false);

  if (force_portal) {
    eraseWifiCredentials();
    WiFi.mode(WIFI_OFF);
    delay(100);
  }

  if (force_portal) {
    Serial.println("Opening WiFi setup portal (after reset)");
    if (openConfigPortal() && wifiLinkUp()) {
      WiFi.setAutoReconnect(true);
      Serial.printf("Connected: %s  IP %s\n", WiFi.SSID().c_str(),
                    WiFi.localIP().toString().c_str());
      return true;
    }
    Serial.println("WiFi connection failed");
    statusScreenConnectFailed();
    return false;
  }

  Serial.println("Connecting to WiFi (portal opens if needed)...");

  if (wifiLinkUp()) {
    WiFi.setAutoReconnect(true);
    Serial.printf("Connected: %s  IP %s\n", WiFi.SSID().c_str(),
                  WiFi.localIP().toString().c_str());
    return true;
  }

  if (storedWifiCredentials() && connectSavedNetwork(true)) {
    WiFi.setAutoReconnect(true);
    Serial.printf("Connected: %s  IP %s\n", WiFi.SSID().c_str(),
                  WiFi.localIP().toString().c_str());
    return true;
  }

  if (connectFallbackNetwork(true)) {
    WiFi.setAutoReconnect(true);
    Serial.printf("Connected with fallback WiFi: %s  IP %s\n",
                  WiFi.SSID().c_str(),
                  WiFi.localIP().toString().c_str());
    return true;
  }

  if (storedWifiCredentials()) {
    Serial.println("Saved and fallback WiFi could not connect — opening setup portal");
  } else {
    Serial.println("No saved or fallback WiFi — opening setup portal");
  }

  if (openConfigPortal() && wifiLinkUp()) {
    WiFi.setAutoReconnect(true);
    Serial.printf("Connected: %s  IP %s\n", WiFi.SSID().c_str(),
                  WiFi.localIP().toString().c_str());
    return true;
  }

  Serial.println("WiFi connection failed");
  statusScreenConnectFailed();
  return false;
}
