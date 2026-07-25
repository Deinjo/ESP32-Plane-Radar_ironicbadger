#pragma once

#include <cstddef>

namespace services::settings {

constexpr size_t kOtaPasswordMaxLen = 32;

/** Load persistent display and OTA settings from NVS. */
void init();

bool footerEnabled();
bool weatherEnabled();
bool temperatureFahrenheit();
bool use24HourClock();
const char* otaPassword();

/**
 * Store web-portal values. An empty OTA password keeps the current password so
 * the portal never needs to echo the stored secret into its HTML.
 */
void saveFromPortal(const char* footer_checkbox, const char* weather_checkbox,
                    const char* fahrenheit_checkbox,
                    const char* clock24_checkbox,
                    const char* ota_password_value);

/** Restore defaults during a full BOOT-button reset. */
void clear();

}  // namespace services::settings
