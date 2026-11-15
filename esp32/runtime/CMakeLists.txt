set(ITO_MAIN "${CMAKE_CURRENT_LIST_DIR}/../firmware/main")
set(ITO_ENGINE "${CMAKE_CURRENT_LIST_DIR}/../engine")
idf_component_register(
    SRCS "${ITO_MAIN}/main.c" "${ITO_MAIN}/guard.c"
         "${ITO_MAIN}/kernels_s3.c" "${ITO_MAIN}/dot_rows_s3.S"
         "${ITO_ENGINE}/itofs.c" "${ITO_ENGINE}/itofs_sched.c"
         "${ITO_ENGINE}/itofs_split.c" "${ITO_ENGINE}/itofs_equiv.c"
    INCLUDE_DIRS "." "${ITO_ENGINE}"
    PRIV_INCLUDE_DIRS "${ITO_MAIN}"
    PRIV_REQUIRES frontend esp_timer esp_driver_uart esp_driver_gpio esp_partition
                  esp_psram heap esp_system spi_flash esp_mm esp_hw_support
                  nvs_flash hal soc esp-nn
    EMBED_TXTFILES "${ITO_MAIN}/phrases.txt")
target_compile_definitions(${COMPONENT_LIB} PRIVATE
    ITOFS_EMBEDDED=1 CONFIG_ITOFS_FRONTEND=1 CONFIG_ITOFS_FE_FAST_FIRST=1
    STEADY_FRAMES=32 FIRST_FRAMES=32 S3_GEMM_DUAL_DEFAULT=0)
target_compile_options(${COMPONENT_LIB} PRIVATE
    -O2 -ffp-contract=off -funroll-loops
    -Wno-unused-function -Wno-format-truncation)
