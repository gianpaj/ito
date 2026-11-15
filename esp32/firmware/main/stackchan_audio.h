#pragma once

#include <stdbool.h>
#include "esp_err.h"

// Prepare power and hold the amplifier in reset before Ito starts its I2S clock.
esp_err_t stackchan_audio_prepare(void);
// Ito supplies 16-bit stereo I2S with identical left/right samples at sample_rate.
esp_err_t stackchan_audio_init(int sample_rate, int volume);
esp_err_t stackchan_audio_mute(bool mute);
esp_err_t stackchan_audio_set_volume(int volume);

// The display shares the board's I2C power and reset controls.
esp_err_t stackchan_lcd_reset(void);
esp_err_t stackchan_lcd_backlight(bool on);
