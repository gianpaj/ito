// StackChan wiring: M5Stack CoreS3 schematic sheets 1, 4, 5 and StackChan Power.
// PY32 register protocol: M5Stack's PY32IOExpander_Class, copyright 2026 M5Stack,
// MIT licensed. See esp32/STACKCHAN.md for source and schematic links.
#include "stackchan_audio.h"
#include "driver/i2c_master.h"
#include "esp_codec_dev_defaults.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

static const char *TAG = "stackchan";
static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_axp, s_aw, s_base;
static const audio_codec_if_t *s_codec;
static SemaphoreHandle_t s_lock;
static bool s_ready, s_muted = true;
static int s_volume;

static esp_err_t add_device(uint8_t address, i2c_master_dev_handle_t *device)
{
    i2c_device_config_t config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = address,
        .scl_speed_hz = 100000,
    };
    return i2c_master_bus_add_device(s_bus, &config, device);
}

static esp_err_t read_reg(i2c_master_dev_handle_t device, uint8_t reg, uint8_t *value)
{
    return i2c_master_transmit_receive(device, &reg, 1, value, 1, 100);
}

static esp_err_t update_reg(i2c_master_dev_handle_t device, uint8_t reg, uint8_t clear, uint8_t set)
{
    uint8_t value;
    esp_err_t error = read_reg(device, reg, &value);
    if (error != ESP_OK) return error;
    const uint8_t data[] = { reg, (value & ~clear) | set };
    return i2c_master_transmit(device, data, sizeof data, 100);
}

static esp_err_t verify_reg(i2c_master_dev_handle_t device, uint8_t reg, uint8_t mask, uint8_t expected)
{
    uint8_t value;
    esp_err_t error = read_reg(device, reg, &value);
    if (error != ESP_OK) return error;
    return (value & mask) == expected ? ESP_OK : ESP_ERR_INVALID_STATE;
}

static esp_err_t fail(const char *step, esp_err_t error)
{
    s_ready = false;
    if (s_aw) (void)update_reg(s_aw, 0x02, 1 << 2, 0);
    ESP_LOGE(TAG, "%s: %s; speaker disabled", step, esp_err_to_name(error));
    return error;
}

#define CHECK_STEP(step, call) do { \
    esp_err_t error_ = (call); \
    if (error_ != ESP_OK) return fail(step, error_); \
} while (0)

esp_err_t stackchan_audio_prepare(void)
{
    i2c_master_bus_config_t config = {
        .i2c_port = I2C_NUM_1,
        .sda_io_num = 12,
        .scl_io_num = 11,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    CHECK_STEP("I2C bus", i2c_new_master_bus(&config, &s_bus));
    CHECK_STEP("AW9523 device", add_device(0x58, &s_aw));
    // P0.2 is AW_RST. Set the output latch before changing direction.
    CHECK_STEP("amplifier reset latch", update_reg(s_aw, 0x02, 1 << 2, 0));
    CHECK_STEP("amplifier GPIO mode", update_reg(s_aw, 0x12, 0, 1 << 2));
    CHECK_STEP("amplifier push-pull", update_reg(s_aw, 0x11, 0, 1 << 4));
    CHECK_STEP("amplifier reset output", update_reg(s_aw, 0x04, 1 << 2, 0));

    CHECK_STEP("PY32 device", add_device(0x6f, &s_base));
    uint8_t version = 0;
    bool base_ready = false;
    const int64_t deadline = esp_timer_get_time() + 1500000;
    do {
        if (i2c_master_probe(s_bus, 0x6f, 50) == ESP_OK &&
            read_reg(s_base, 0x02, &version) == ESP_OK && version && version != 0xff) {
            base_ready = true;
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    } while (esp_timer_get_time() < deadline);
    if (!base_ready) return fail("PY32 startup", ESP_ERR_TIMEOUT);
    // IO1 is VM_EN. Drive it low without enabling the motor or touching RGB.
    CHECK_STEP("motor power latch", update_reg(s_base, 0x05, 1, 0));
    CHECK_STEP("motor push-pull", update_reg(s_base, 0x13, 1, 0));
    CHECK_STEP("motor pull-up off", update_reg(s_base, 0x09, 1, 0));
    CHECK_STEP("motor pull-down", update_reg(s_base, 0x0b, 0, 1));
    CHECK_STEP("motor power output", update_reg(s_base, 0x03, 0, 1));
    CHECK_STEP("motor latch readback", verify_reg(s_base, 0x05, 1, 0));
    CHECK_STEP("motor direction readback", verify_reg(s_base, 0x03, 1, 1));

    CHECK_STEP("AXP2101 device", add_device(0x34, &s_axp));
    uint8_t chip_id;
    CHECK_STEP("AXP2101 identity", read_reg(s_axp, 0x03, &chip_id));
    if (chip_id != 0x4a) return fail("AXP2101 identity", ESP_ERR_NOT_SUPPORTED);
    // ALDO1 supplies AW88298 DVDD at 1.8 V. ALDO2 supplies the ADC/microphones;
    // DLDO1 supplies the backlight. Keep both off and preserve other rails.
    CHECK_STEP("amplifier 1.8 V", update_reg(s_axp, 0x92, 0x1f, 13));
    CHECK_STEP("power rails", update_reg(s_axp, 0x90, (1 << 7) | (1 << 1), 1));
    CHECK_STEP("power rail readback", verify_reg(s_axp, 0x90, (1 << 7) | (1 << 1) | 1, 1));
    s_lock = xSemaphoreCreateMutex();
    if (!s_lock) return fail("codec mutex", ESP_ERR_NO_MEM);
    ESP_LOGI(TAG, "AXP2101 0x34, AW9523 0x58, PY32 0x6f version 0x%02x; motors off, backlight off, microphone rail off", version);
    return ESP_OK;
}

static esp_err_t codec_result(int result)
{
    return result == ESP_CODEC_DEV_OK ? ESP_OK : ESP_FAIL;
}

esp_err_t stackchan_audio_init(int sample_rate, int volume)
{
    if (!s_lock || sample_rate != 24000 || volume < 0 || volume > 100) return ESP_ERR_INVALID_ARG;
    // Ito has enabled I2S with an empty DMA queue. Keep it silent throughout setup.
    CHECK_STEP("release amplifier reset", update_reg(s_aw, 0x02, 0, 1 << 2));
    vTaskDelay(pdMS_TO_TICKS(50));
    CHECK_STEP("AW88298 probe", i2c_master_probe(s_bus, AW88298_CODEC_DEFAULT_ADDR >> 1, 100));
    audio_codec_i2c_cfg_t control_config = {
        .port = I2C_NUM_1,
        .addr = AW88298_CODEC_DEFAULT_ADDR,
        .bus_handle = s_bus,
    };
    const audio_codec_ctrl_if_t *control = audio_codec_new_i2c_ctrl(&control_config);
    if (!control) return fail("codec control", ESP_ERR_NO_MEM);
    aw88298_codec_cfg_t codec_config = {
        .ctrl_if = control,
        .reset_pin = -1,
        .hw_gain = { .pa_voltage = 5.0f, .codec_dac_voltage = 3.3f, .pa_gain = 1.0f },
    };
    s_codec = aw88298_codec_new(&codec_config);
    if (!s_codec) return fail("AW88298 initialization", ESP_FAIL);
    CHECK_STEP("initial mute", codec_result(s_codec->mute(s_codec, true)));
    esp_codec_dev_sample_info_t format = {
        .sample_rate = sample_rate,
        .bits_per_sample = 16,
        .channel = 2,
        .mclk_multiple = 256,
    };
    CHECK_STEP("codec format", codec_result(s_codec->set_fs(s_codec, &format)));
    CHECK_STEP("initial volume", codec_result(s_codec->set_vol(s_codec, (volume - 100) * 0.5f)));
    CHECK_STEP("enable amplifier", codec_result(s_codec->enable(s_codec, true)));
    s_volume = volume;
    s_muted = true;
    s_ready = true;
    ESP_LOGI(TAG, "AW88298 ready: 24000 Hz, 16-bit stereo, duplicated mono, volume %d, muted; GPIO0 is MCLK", volume);
    return ESP_OK;
}

esp_err_t stackchan_audio_mute(bool mute)
{
    if (!s_lock) return ESP_ERR_INVALID_STATE;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    esp_err_t error = ESP_ERR_INVALID_STATE;
    if (s_ready) {
        s_muted = mute;
        error = codec_result(s_codec->mute(s_codec, mute || s_volume == 0));
        if (error != ESP_OK) fail("codec mute", error);
    }
    xSemaphoreGive(s_lock);
    return error;
}

esp_err_t stackchan_audio_set_volume(int volume)
{
    if (volume < 0 || volume > 100) return ESP_ERR_INVALID_ARG;
    if (!s_lock) return ESP_ERR_INVALID_STATE;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    esp_err_t error = ESP_ERR_INVALID_STATE;
    if (s_ready) {
        error = codec_result(s_codec->set_vol(s_codec, (volume - 100) * 0.5f));
        if (error == ESP_OK) error = codec_result(s_codec->mute(s_codec, s_muted || volume == 0));
        if (error == ESP_OK) s_volume = volume;
        else fail("codec volume", error);
    }
    xSemaphoreGive(s_lock);
    return error;
}

esp_err_t stackchan_lcd_reset(void)
{
    if (!s_lock || !s_aw) return ESP_ERR_INVALID_STATE;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    // AW9523 P1.1 is LCD_RST. Preserve all other expander outputs.
    esp_err_t error = update_reg(s_aw, 0x03, 1 << 1, 0);
    if (error == ESP_OK) error = update_reg(s_aw, 0x13, 0, 1 << 1);
    if (error == ESP_OK) error = update_reg(s_aw, 0x05, 1 << 1, 0);
    if (error == ESP_OK) {
        vTaskDelay(pdMS_TO_TICKS(20));
        error = update_reg(s_aw, 0x03, 0, 1 << 1);
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    if (error == ESP_OK) error = verify_reg(s_aw, 0x03, 1 << 1, 1 << 1);
    xSemaphoreGive(s_lock);
    return error;
}

esp_err_t stackchan_lcd_backlight(bool on)
{
    if (!s_lock || !s_axp) return ESP_ERR_INVALID_STATE;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    // The factory brightness map uses register values 20..28. Use 26.
    esp_err_t error = on ? update_reg(s_axp, 0x99, 0x1f, 26) : ESP_OK;
    if (error == ESP_OK) error = update_reg(s_axp, 0x90, 1 << 7, on ? 1 << 7 : 0);
    if (error == ESP_OK) error = verify_reg(s_axp, 0x90, 1 << 7, on ? 1 << 7 : 0);
    xSemaphoreGive(s_lock);
    return error;
}
