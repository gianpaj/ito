/* Production lifecycle bodies; only OS, codec and inference construction are mocked. */
#include "itofs_service.h"
#include <assert.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_ERR_TIMEOUT 0x107
#define pdTRUE 1
#define pdMS_TO_TICKS(n) (n)
#define portMAX_DELAY -1
#define MALLOC_CAP_INTERNAL 1
#define MALLOC_CAP_8BIT 2
#define MALLOC_CAP_SPIRAM 4
#define NBUF 6
#define PARK_FE 1u
#define PARK_SYNTH 2u
#define PARK_PLAY 4u
static atomic_int s_service_up, s_boot_done, s_fe_abort, s_park_error;
static atomic_uint s_park_epoch[3], s_stop_sequence, s_fe_job, s_job_generation;
static unsigned s_workers;
static int s_service_started, s_stopped, s_hot_borrowed;
static void *s_hot, *s_bulk, *s_wbuf, *s_text_pcm, *s_pcm_buffers[NBUF];
static size_t s_hot_reserved, s_blob_size;
static const void *s_blob;
static const int *s_st, *s_st16;
static int s_mapped, s_map_h, s_ndemo, s_demo_from_blob;
static int s_cancel, s_speaking, s_playing, s_style, s_resume_style, s_resume_act;
static uint32_t s_active_job;
static int64_t s_cancel_t, clock_us;
static struct { int act_bits; unsigned char data[64]; } s_ctx;
static struct { unsigned char data[64]; } s_model;
static int queues[5], mutex;
static int *s_free_q=&queues[0], *s_full_q=&queues[1], *s_done_q=&queues[2],
           *s_req_q=&queues[3], *s_fe_q=&queues[4], *s_command_mutex;
static itofs_service_config_t s_audio;
static int live_blocks, fail_allocation, allocation_index, fail_mutex, mutex_timeout;
static int park_after_delay, flush_error, mute_error, flushes, unmapped;
static int runtime_calls, runtime_error, stop_during_start, taint_during_start, opens, volumes;
static void *owned[64];
static size_t free_psram, last_allocation_size;
static size_t heap_caps_get_free_size(int caps) { assert(caps==MALLOC_CAP_SPIRAM); return free_psram; }
static int64_t esp_timer_get_time(void) { return clock_us; }
static void acknowledge_workers(void) {
    for (int i=0;i<3;i++) atomic_store(&s_park_epoch[i],atomic_load(&s_stop_sequence));
}
static void clear_acknowledgements(void) {
    for (int i=0;i<3;i++) atomic_store(&s_park_epoch[i],~atomic_load(&s_stop_sequence));
}
static void vTaskDelay(int ms) {
    clock_us += (int64_t)ms * 1000;
    if (park_after_delay) acknowledge_workers();
}
static void *heap_caps_aligned_alloc(size_t alignment, size_t size, int caps) {
    (void)alignment; (void)caps;
    last_allocation_size=size;
    if (++allocation_index == fail_allocation) return NULL;
    void *p=malloc(size); assert(p);
    for (int i=0;i<64;i++) if (!owned[i]) { owned[i]=p; live_blocks++; return p; }
    abort();
}
static void heap_caps_free(void *p) {
    if (!p) return;
    for (int i=0;i<64;i++) if (owned[i]==p) { owned[i]=NULL; live_blocks--; free(p); return; }
    assert(!"free of unowned allocation");
}
static void *xSemaphoreCreateMutex(void) { return fail_mutex ? NULL : &mutex; }
static int xSemaphoreTake(void *p, int timeout) {
    (void)timeout; assert(p==&mutex);
    return !mutex_timeout;
}
static void xSemaphoreGive(void *p) { assert(p==&mutex); }
static void xQueueReset(int *q) { *q=0; }
static void esp_partition_munmap(int handle) { assert(handle==7); unmapped++; }
static void guard_set_watchdog_hooks(void *u, void (*arm)(void *,uint32_t), void (*feed)(void *)) {
    (void)u; (void)arm; (void)feed;
}
static esp_err_t open_audio(void *u,int rate) { (void)u;(void)rate;opens++;return ESP_OK; }
static esp_err_t write_audio(void *u,const int16_t *p,size_t n) { (void)u;(void)p;(void)n;return ESP_OK; }
static esp_err_t drain_audio(void *u) { (void)u;return ESP_OK; }
static esp_err_t flush_audio(void *u) { (void)u;flushes++;return flush_error; }
static esp_err_t mute_audio(void *u,bool muted) { (void)u;assert(muted);return mute_error; }
static esp_err_t volume_audio(void *u,int v) { (void)u;(void)v;volumes++;return ESP_OK; }
static void playing_audio(void *u,bool playing) { (void)u;assert(!playing); }
static itofs_service_config_t config = {.open=open_audio,.write=write_audio,.drain=drain_audio,
    .flush=flush_audio,.mute=mute_audio,.set_volume=volume_audio,.playing=playing_audio};
static void request_stop(void);
static esp_err_t runtime_start(void) {
    /* Model/allocator dependency seam: partial allocations fail at each boundary. */
    runtime_calls++;
    if (taint_during_start) atomic_store(&s_park_error,ESP_FAIL);
    void **slots[]={&s_bulk,&s_wbuf,&s_text_pcm,&s_pcm_buffers[0],&s_pcm_buffers[1],
        &s_pcm_buffers[2],&s_pcm_buffers[3],&s_pcm_buffers[4],&s_pcm_buffers[5]};
    s_mapped=1;s_map_h=7;s_blob=&s_model;s_blob_size=17;
    s_st=s_st16=(const int *)&s_model;s_ndemo=s_demo_from_blob=1;
    for (size_t i=0;i<sizeof slots/sizeof slots[0];i++) {
        *slots[i]=heap_caps_aligned_alloc(16,128,0);
        if (!*slots[i]) return ESP_ERR_NO_MEM;
    }
    memset(s_hot,0x39,s_hot_reserved);
    memset(&s_ctx,0x39,sizeof s_ctx);memset(&s_model,0x39,sizeof s_model);
    s_ctx.act_bits=8;
    if (stop_during_start) request_stop();
    return runtime_error;
}
#include "production_functions.inc"

static void fresh(void) {
    assert(!live_blocks);
    s_hot=s_bulk=s_wbuf=s_text_pcm=NULL;
    memset(s_pcm_buffers,0,sizeof s_pcm_buffers);
    s_hot_reserved=0;s_service_started=s_stopped=s_hot_borrowed=0;
    s_workers=PARK_FE|PARK_SYNTH|PARK_PLAY;
    acknowledge_workers();atomic_store(&s_stop_sequence,0);
    atomic_store(&s_service_up,0);
    atomic_store(&s_boot_done,0);atomic_store(&s_fe_job,0);atomic_store(&s_park_error,0);
    fail_allocation=allocation_index=fail_mutex=mutex_timeout=0;
    park_after_delay=1;flush_error=mute_error=0;runtime_error=0;stop_during_start=taint_during_start=0;
    s_mapped=0;clock_us=0;runtime_calls=0;
    assert(itofs_service_reserve_hot(239948)==ESP_OK);
}
static void cleanup(void) {
    park_after_delay=1;acknowledge_workers();assert(itofs_service_stop(100)==ESP_OK);
    assert(live_blocks==1);heap_caps_free(s_hot);s_hot=NULL;assert(!live_blocks);
}
static void assert_released(void) {
    assert(s_stopped && !s_bulk && !s_wbuf && !s_text_pcm && !s_mapped);
    assert(!s_blob && !s_blob_size && !s_st && !s_st16 && !s_ndemo && !s_demo_from_blob);
    for (int i=0;i<NBUF;i++) assert(!s_pcm_buffers[i]);
    for (int i=0;i<5;i++) assert(queues[i]==0);
    assert(!atomic_load(&s_fe_job) && !s_cancel && !s_speaking && !s_playing && !s_active_job);
    for (size_t i=0;i<sizeof s_ctx;i++) assert(((unsigned char *)&s_ctx)[i]==0);
    for (size_t i=0;i<sizeof s_model;i++) assert(((unsigned char *)&s_model)[i]==0);
    assert(live_blocks==1 && s_hot);
}
int main(void) {
    const size_t extent=3196096, bulk_bytes=1579920, need=extent+64+bulk_bytes+320*1024;
    free_psram=need-1;
    assert(!allocate_weight_copy(extent,bulk_bytes) && !s_wbuf && allocation_index==0);
    free_psram=7979384;
    assert(allocate_weight_copy(extent,bulk_bytes) && last_allocation_size==extent+64);
    heap_caps_free(s_wbuf);s_wbuf=NULL;
    fail_allocation=allocation_index+1;
    assert(!allocate_weight_copy(extent,bulk_bytes) && !s_wbuf);
    fail_allocation=0;
    puts("PASS weight-copy allocation uses total budget, attempts only its own block and respects allocation failure");
    fresh();
    assert(itofs_service_start(NULL)==ESP_ERR_INVALID_ARG);
    fail_mutex=1;assert(itofs_service_start(&config)==ESP_ERR_NO_MEM);
    fail_mutex=0;assert(itofs_service_start(&config)==ESP_OK);
    assert(itofs_service_start(&config)==ESP_ERR_INVALID_STATE);
    cleanup();puts("PASS start validation, mutex failure and duplicate start");

    for (int failure=1;failure<=9;failure++) {
        fresh();fail_allocation=allocation_index+failure;
        assert(itofs_service_start(&config)==ESP_ERR_NO_MEM);assert_released();
        fail_allocation=0;assert(itofs_service_resume()==ESP_OK);
        assert(atomic_load(&s_service_up));cleanup();
    }
    puts("PASS every partial allocation failure releases ownership and resume retries");

    fresh();assert(itofs_service_start(&config)==ESP_OK);
    park_after_delay=0;clear_acknowledgements();void *bulk=s_bulk;int blocks=live_blocks;
    assert(itofs_service_stop(20)==ESP_ERR_TIMEOUT);
    assert(live_blocks==blocks && s_bulk==bulk && !s_stopped && !atomic_load(&s_service_up));
    void *workspace=NULL;size_t bytes=0;
    assert(itofs_service_borrow_hot(&workspace,&bytes)==ESP_ERR_INVALID_STATE);
    assert(itofs_service_resume()==ESP_ERR_INVALID_STATE);
    park_after_delay=1;acknowledge_workers();assert(itofs_service_stop(20)==ESP_OK);assert_released();
    assert(itofs_service_borrow_hot(&workspace,&bytes)==ESP_OK && workspace==s_hot && bytes==239948);
    assert(itofs_service_borrow_hot(&workspace,&bytes)==ESP_ERR_INVALID_STATE);
    assert(itofs_service_resume()==ESP_ERR_INVALID_STATE);
    memset(workspace,0xa5,bytes);
    assert(itofs_service_return_hot((char *)workspace+1)==ESP_ERR_INVALID_STATE);
    assert(itofs_service_return_hot(workspace)==ESP_OK);
    assert(itofs_service_return_hot(workspace)==ESP_ERR_INVALID_STATE);
    assert(itofs_service_resume()==ESP_OK);
    for (size_t i=0;i<bytes;i++) assert(((unsigned char *)workspace)[i]==0x39);
    cleanup();puts("PASS timeout retains ownership; exclusive borrow, overwrite and resume");

    fresh();assert(itofs_service_start(&config)==ESP_OK);
    acknowledge_workers();flush_error=ESP_FAIL;bulk=s_bulk;blocks=live_blocks;
    assert(itofs_service_stop(20)==ESP_FAIL && s_bulk==bulk && live_blocks==blocks);
    flush_error=0;mute_error=ESP_FAIL;
    assert(itofs_service_stop(20)==ESP_FAIL && s_bulk==bulk && live_blocks==blocks);
    mute_error=0;cleanup();puts("PASS codec flush/mute errors retain inference ownership");

    fresh();assert(itofs_service_start(&config)==ESP_OK);
    mutex_timeout=1;bulk=s_bulk;blocks=live_blocks;
    assert(itofs_service_stop(20)==ESP_ERR_TIMEOUT && s_bulk==bulk && live_blocks==blocks);
    mutex_timeout=0;cleanup();puts("PASS command-lock timeout retains inference ownership");

    fresh();stop_during_start=1;assert(itofs_service_start(&config)==ESP_ERR_INVALID_STATE);
    assert_released();stop_during_start=0;assert(itofs_service_resume()==ESP_OK);cleanup();
    puts("PASS stop sequence invalidates initialization before admission opens");

    fresh();assert(itofs_service_start(&config)==ESP_OK);
    assert(itofs_service_stop(20)==ESP_OK);stop_during_start=1;
    assert(itofs_service_resume()==ESP_ERR_INVALID_STATE);assert_released();
    stop_during_start=0;assert(itofs_service_resume()==ESP_OK);cleanup();
    puts("PASS stop sequence invalidates resume before admission opens");

    fresh();assert(itofs_service_start(&config)==ESP_OK);
    acknowledge_workers();assert(itofs_service_stop(20)==ESP_OK);
    fail_allocation=allocation_index+3;park_after_delay=0;clear_acknowledgements();
    assert(itofs_service_resume()==ESP_ERR_TIMEOUT && !s_stopped && s_bulk && !atomic_load(&s_service_up));
    fail_allocation=0;park_after_delay=1;acknowledge_workers();assert(itofs_service_stop(20)==ESP_OK);
    assert_released();park_after_delay=1;assert(itofs_service_resume()==ESP_OK);cleanup();
    puts("PASS failed resume cleanup timeout preserves memory until stop retry");

    fresh();assert(itofs_service_start(&config)==ESP_OK);
    for (int cycle=0;cycle<100;cycle++) {
        for (int i=0;i<5;i++) queues[i]=9;
        atomic_store(&s_fe_job,17);s_active_job=17;s_speaking=s_playing=1;
        assert(itofs_service_stop(20)==ESP_OK);assert_released();
        assert(itofs_service_borrow_hot(&workspace,&bytes)==ESP_OK);
        memset(workspace,cycle,bytes);assert(itofs_service_return_hot(workspace)==ESP_OK);
        assert(itofs_service_resume()==ESP_OK && live_blocks==10);
    }
    cleanup();assert(opens==0 && volumes==0);
    puts("PASS 100 stop/borrow/overwrite/return/resume cycles without leaks or codec reconfiguration");
    fresh();assert(itofs_service_start(&config)==ESP_OK);
    atomic_store(&s_park_error,ESP_FAIL);bulk=s_bulk;blocks=live_blocks;int old_flushes=flushes;
    assert(itofs_service_stop(20)==ESP_FAIL);
    assert(flushes==old_flushes+1 && s_bulk==bulk && live_blocks==blocks && !s_stopped);
    assert(!atomic_load(&s_service_up));
    assert(itofs_service_borrow_hot(&workspace,&bytes)==ESP_ERR_INVALID_STATE);
    assert(itofs_service_resume()==ESP_FAIL);
    assert(itofs_service_stop(20)==ESP_FAIL && s_bulk==bulk && live_blocks==blocks);
    /* Only fixture shutdown simulates a reboot; production cannot release tainted DMA storage. */
    for (int i=0;i<64;i++) if (owned[i]) heap_caps_free(owned[i]);
    puts("PASS fatal DMA park taint retains all ownership across stop retries and blocks borrow/resume");

    fresh();atomic_store(&s_park_error,ESP_FAIL);fail_allocation=allocation_index+3;
    assert(itofs_service_start(&config)==ESP_FAIL && s_bulk && live_blocks==3 && !s_stopped);
    assert(itofs_service_stop(20)==ESP_FAIL && live_blocks==3);
    assert(itofs_service_borrow_hot(&workspace,&bytes)==ESP_ERR_INVALID_STATE);
    assert(itofs_service_resume()==ESP_FAIL);
    for (int i=0;i<64;i++) if (owned[i]) heap_caps_free(owned[i]);
    puts("PASS initialization cleanup preserves partial storage when DMA park is tainted");
    fresh();assert(itofs_service_start(&config)==ESP_OK);assert(itofs_service_stop(20)==ESP_OK);
    taint_during_start=1;fail_allocation=allocation_index+3;
    assert(itofs_service_resume()==ESP_FAIL && s_bulk && live_blocks==3 && !s_stopped);
    assert(itofs_service_stop(20)==ESP_FAIL && live_blocks==3);
    assert(itofs_service_borrow_hot(&workspace,&bytes)==ESP_ERR_INVALID_STATE);
    assert(itofs_service_resume()==ESP_FAIL);
    for (int i=0;i<64;i++) if (owned[i]) heap_caps_free(owned[i]);
    puts("PASS resume cleanup preserves partial storage when DMA park becomes tainted");
    return 0;
}
