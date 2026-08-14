#pragma once

#include <Print.h>

namespace ui {

/** Draw the static sonar/radar grid (black disc, green overlay, labels). */
void radarDisplayDraw();

/** Redraw aircraft only (blits cached grid; no full-screen clear). */
void radarDisplayRefreshAircraft();

/** Update the display when the configured night-mode boundary is crossed. */
void radarDisplayTick();

/** Stream the current 240x240 display frame as a 24-bit BMP image. */
void radarDisplayWriteBmp(Print& output);

/** Return whether at least one complete display frame has been rendered. */
bool radarDisplayFrameReady();

}  // namespace ui
