#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* One runtime per device. The application owns its codec, NVS and watchdog.
 * Callbacks run on runtime tasks; playing must dispatch UI work safely.
 * write consumes mono int16 PCM before returning. drain waits for the final
 * sample at the speaker. flush drops pending output and silences the speaker.
 * mute must preserve the volume chosen by set_volume. */
typedef struct {
    void *user;
    esp_err_t (*open)(void *user, int sample_rate);
    esp_err_t (*write)(void *user, const int16_t *pcm, size_t samples);
    esp_err_t (*drain)(void *user);
    esp_err_t (*flush)(void *user);
    esp_err_t (*mute)(void *user, bool muted);
    esp_err_t (*set_volume)(void *user, int percent);
    void (*playing)(void *user, bool playing);
    void (*watchdog_arm)(void *user, uint32_t timeout_ms);
    void (*watchdog_feed)(void *user);
    bool start_console;
} itofs_service_config_t;

/* Optional early allocation before the display fragments internal SRAM.
 * The 32-frame female int4 profile needs 239948 bytes. start checks the size
 * against the actual model and never moves the hot arena into PSRAM. */
esp_err_t itofs_service_reserve_hot(size_t bytes);
/* Starts initialization asynchronously. READY reports completed self-tests and
 * calibration. Repeated calls return ESP_ERR_INVALID_STATE. There is no second
 * codec or I2S initialization in this component. */
esp_err_t itofs_service_start(const itofs_service_config_t *config);
/* Submit a serial command without owning UART/USB. Calls are serialized inside
 * the runtime. Text is rejected while another text job remains active.
 * This function can wait for the bounded request queue; call it off the UI. */
esp_err_t itofs_service_command(const char *line);
/* Invalidates the active text job and queued utterances. Output is flushed by
 * the playback worker, whose writes are at most 20 ms of audio each. */
void itofs_service_cancel(void);

#ifdef __cplusplus
}
#endif
