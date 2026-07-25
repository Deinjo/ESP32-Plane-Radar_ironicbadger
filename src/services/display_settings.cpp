#include "services/display_settings.h"

#include <Preferences.h>

#include <cctype>
#include <cstring>

#include "config.h"

namespace services::settings {
namespace {

constexpr char kPrefsNamespace[] = "display";
constexpr char kKeyFooter[] = "footer";
constexpr char kKeyWeather[] = "weather";
constexpr char kKeyFahrenheit[] = "tempF";
constexpr char kKeyClock24[] = "time24";
constexpr char kKeyOtaPassword[] = "otaPass";

char s_ota_password[kOtaPasswordMaxLen + 1] = {};
bool s_footer_enabled = true;
bool s_weather_enabled = true;
bool s_temperature_fahrenheit = false;
bool s_use_24_hour_clock = true;

bool checkboxChecked(const char* value) {
  if (value == nullptr || value[0] == '\0') {
    return false;
  }
  return strcmp(value, "on") == 0 || strcmp(value, "T") == 0 ||
         strcmp(value, "t") == 0 || strcmp(value, "F") == 0 ||
         strcmp(value, "f") == 0;
}

void copyCleanText(const char* value, char* out, size_t out_len) {
  if (out_len == 0) {
    return;
  }
  out[0] = '\0';
  if (value == nullptr) {
    return;
  }

  size_t written = 0;
  bool previous_space = true;
  for (size_t i = 0; value[i] != '\0' && written + 1 < out_len; ++i) {
    const unsigned char ch = static_cast<unsigned char>(value[i]);
    if (std::isspace(ch)) {
      if (!previous_space) {
        out[written++] = ' ';
        previous_space = true;
      }
      continue;
    }
    if (ch >= 32 && ch <= 126) {
      out[written++] = static_cast<char>(ch);
      previous_space = false;
    }
  }
  while (written > 0 && out[written - 1] == ' ') {
    --written;
  }
  out[written] = '\0';
}

void loadDefaults() {
  copyCleanText(config::kDefaultOtaPassword, s_ota_password,
                sizeof(s_ota_password));
  s_footer_enabled = true;
  s_weather_enabled = true;
  s_temperature_fahrenheit = false;
  s_use_24_hour_clock = true;
}

void persist() {
  Preferences prefs;
  if (!prefs.begin(kPrefsNamespace, false)) {
    return;
  }
  prefs.putBool(kKeyFooter, s_footer_enabled);
  prefs.putBool(kKeyWeather, s_weather_enabled);
  prefs.putBool(kKeyFahrenheit, s_temperature_fahrenheit);
  prefs.putBool(kKeyClock24, s_use_24_hour_clock);
  prefs.putString(kKeyOtaPassword, s_ota_password);
  prefs.end();
}

}  // namespace

void init() {
  loadDefaults();

  Preferences prefs;
  if (!prefs.begin(kPrefsNamespace, true)) {
    return;
  }

  s_footer_enabled = prefs.getBool(kKeyFooter, true);
  s_weather_enabled = prefs.getBool(kKeyWeather, true);
  s_temperature_fahrenheit = prefs.getBool(kKeyFahrenheit, false);
  s_use_24_hour_clock = prefs.getBool(kKeyClock24, true);

  String value = prefs.getString(kKeyOtaPassword, config::kDefaultOtaPassword);
  copyCleanText(value.c_str(), s_ota_password, sizeof(s_ota_password));
  if (s_ota_password[0] == '\0') {
    copyCleanText(config::kDefaultOtaPassword, s_ota_password,
                  sizeof(s_ota_password));
  }
  prefs.end();
}

bool footerEnabled() { return s_footer_enabled; }

bool weatherEnabled() { return s_weather_enabled; }

bool temperatureFahrenheit() { return s_temperature_fahrenheit; }

bool use24HourClock() { return s_use_24_hour_clock; }

const char* otaPassword() { return s_ota_password; }

void saveFromPortal(const char* footer_checkbox, const char* weather_checkbox,
                    const char* fahrenheit_checkbox,
                    const char* clock24_checkbox,
                    const char* ota_password_value) {
  s_footer_enabled = checkboxChecked(footer_checkbox);
  s_weather_enabled = checkboxChecked(weather_checkbox);
  s_temperature_fahrenheit = checkboxChecked(fahrenheit_checkbox);
  s_use_24_hour_clock = checkboxChecked(clock24_checkbox);

  char password[kOtaPasswordMaxLen + 1] = {};
  copyCleanText(ota_password_value, password, sizeof(password));
  if (password[0] != '\0') {
    strncpy(s_ota_password, password, sizeof(s_ota_password) - 1);
    s_ota_password[sizeof(s_ota_password) - 1] = '\0';
  }

  persist();
  Serial.printf("Display footer: %s, weather: %s\n",
                s_footer_enabled ? "on" : "off",
                s_weather_enabled ? "on" : "off");
}

void clear() {
  Preferences prefs;
  if (prefs.begin(kPrefsNamespace, false)) {
    prefs.clear();
    prefs.end();
  }
  loadDefaults();
}

}  // namespace services::settings
