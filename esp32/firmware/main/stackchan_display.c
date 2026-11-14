// LCD wiring and reset sequence follow M5Stack's MIT-licensed
// StackChan/firmware/main/hal/board/stackchan.cc. See esp32/STACKCHAN.md.
#include "stackchan_display.h"
#include "stackchan_audio.h"
#include "driver/spi_master.h"
#include "esp_heap_caps.h"
#include "esp_lcd_ili9341.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_log.h"

static const char *TAG = "stackchan_display";
static bool s_ready, s_playing;

esp_err_t stackchan_display_init(void)
{
    enum { WIDTH = 320, HEIGHT = 240, RADIUS = 20 };
    esp_lcd_panel_io_handle_t io = NULL;
    esp_lcd_panel_handle_t panel = NULL;
    bool bus_ready = false;
    uint16_t *row = NULL;
    esp_err_t error;
#define LCD_TRY(call) do { error = (call); if (error != ESP_OK) goto fail; } while (0)
    LCD_TRY(stackchan_lcd_backlight(false));
    spi_bus_config_t bus = {
        .mosi_io_num = 37, .miso_io_num = -1, .sclk_io_num = 36,
        .quadwp_io_num = -1, .quadhd_io_num = -1,
        .max_transfer_sz = WIDTH * sizeof(uint16_t),
    };
    LCD_TRY(spi_bus_initialize(SPI3_HOST, &bus, SPI_DMA_CH_AUTO));
    bus_ready = true;
    esp_lcd_panel_io_spi_config_t config = {
        .cs_gpio_num = 3, .dc_gpio_num = 35, .spi_mode = 2,
        .pclk_hz = 40000000, .trans_queue_depth = 1,
        .lcd_cmd_bits = 8, .lcd_param_bits = 8,
    };
    LCD_TRY(esp_lcd_new_panel_io_spi(SPI3_HOST, &config, &io));
    esp_lcd_panel_dev_config_t device = {
        .reset_gpio_num = -1, .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_BGR,
        .bits_per_pixel = 16,
    };
    LCD_TRY(esp_lcd_new_panel_ili9341(io, &device, &panel));
    LCD_TRY(esp_lcd_panel_reset(panel));
    LCD_TRY(stackchan_lcd_reset());
    LCD_TRY(esp_lcd_panel_init(panel));
    LCD_TRY(esp_lcd_panel_invert_color(panel, true));
    LCD_TRY(esp_lcd_panel_swap_xy(panel, false));
    LCD_TRY(esp_lcd_panel_mirror(panel, false, false));
    row = heap_caps_malloc(WIDTH * sizeof(uint16_t), MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if (!row) { error = ESP_ERR_NO_MEM; goto fail; }
    for (int y = 0; y < HEIGHT; y++) {
        for (int x = 0; x < WIDTH; x++) {
            const int dx = x - WIDTH / 2, dy = y - HEIGHT / 2;
            row[x] = dx * dx + dy * dy <= RADIUS * RADIUS ? __builtin_bswap16(0x07e0) : 0;
        }
        LCD_TRY(esp_lcd_panel_draw_bitmap(panel, 0, y, WIDTH, y + 1, row));
        // tx_param drains queued color transfers before this row is reused.
        LCD_TRY(esp_lcd_panel_io_tx_param(io, -1, NULL, 0));
    }
    LCD_TRY(esp_lcd_panel_disp_on_off(panel, true));
    heap_caps_free(row);
    s_ready = true;
    ESP_LOGI(TAG, "green playback dot ready; backlight off while idle");
    return ESP_OK;
fail:
    if (io) (void)esp_lcd_panel_io_tx_param(io, -1, NULL, 0);
    heap_caps_free(row);
    (void)stackchan_lcd_backlight(false);
    if (panel) esp_lcd_panel_del(panel);
    if (io) esp_lcd_panel_io_del(io);
    if (bus_ready) spi_bus_free(SPI3_HOST);
    ESP_LOGW(TAG, "playback indicator unavailable: %s", esp_err_to_name(error));
    return error;
#undef LCD_TRY
}

void stackchan_display_playing(bool playing)
{
    if (!s_ready || s_playing == playing) return;
    const esp_err_t error = stackchan_lcd_backlight(playing);
    if (error != ESP_OK) {
        s_ready = false;
        (void)stackchan_lcd_backlight(false);
        ESP_LOGW(TAG, "playback indicator disabled: %s", esp_err_to_name(error));
        return;
    }
    s_playing = playing;
    ESP_LOGI(TAG, "playing=%d", playing);
}
