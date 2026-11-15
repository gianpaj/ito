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
/* Size and allocate on the caller, then run self-tests/calibration on workers.
 * Call start/resume from a control task with at least 8192 bytes of internal
 * stack for the 32-frame profile. Model layout exceeds a 4096-byte caller stack;
 * flash APIs also require the caller stack to stay in internal RAM. Measure
 * caller stack high-water use during integration. READY reports completed
 * self-tests/calibration. Repeated calls return ESP_ERR_INVALID_STATE. There is
 * no second codec or I2S initialization in this component. */
esp_err_t itofs_service_start(const itofs_service_config_t *config);
/* Close admission, cancel and flush output, then park inference workers before
 * freeing weights, bulk, PCM and quiet-text scratch. The early hot reservation,
 * frontend state/stack, worker stacks, queues, kernel tiles and GDMA stay owned.
 * Initial calibration or an application callback can delay parking. A timeout
 * leaves admission closed and all memory owned; retry stop before borrowing or
 * resuming. A DMA error returns ESP_FAIL and retains inference storage until
 * reboot because completion cannot be proved. Application callbacks must finish
 * cooperatively. The console stays
 * alive, so the control task may call stop without deleting its own task. */
esp_err_t itofs_service_stop(uint32_t timeout_ms);
/* Reacquire inference storage and reinitialize the engine over the retained hot
 * reservation. Calibration and guard records persist. Does not reopen the
 * codec or change volume. Allocation failure leaves workers stopped and can be
 * retried. A timeout during failure cleanup requires another successful stop.
 * The caller stack requirement is documented with start. These calls serialize
 * with commands. Do not call from runtime callbacks. */
esp_err_t itofs_service_resume(void);
/* Borrow only after successful stop. The caller exclusively owns these bytes
 * until returning the same pointer, and must not retain derived pointers after
 * return. Resume rejects an outstanding borrow. This memory never enters the
 * general heap; the application must not free it. */
esp_err_t itofs_service_borrow_hot(void **workspace, size_t *bytes);
esp_err_t itofs_service_return_hot(void *workspace);
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
