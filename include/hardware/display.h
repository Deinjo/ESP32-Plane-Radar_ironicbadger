#pragma once

#include <cstdint>

#include "hardware/lgfx_config.hpp"

extern LGFX tft;

void displayInit();
void displaySetBrightness(uint8_t brightness);
