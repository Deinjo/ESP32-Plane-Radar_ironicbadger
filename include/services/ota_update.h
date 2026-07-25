#pragma once

class WiFiManager;

namespace services::ota {

/** Add an authenticated firmware page to the WiFiManager portal. */
void configure(WiFiManager& manager);

/** True while an OTA upload is actively writing flash. */
bool inProgress();

}  // namespace services::ota
