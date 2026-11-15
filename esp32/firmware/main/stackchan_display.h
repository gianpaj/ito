#pragma once

#include <stdbool.h>
#include "esp_err.h"

esp_err_t stackchan_display_init(void);
void stackchan_display_playing(bool playing);
