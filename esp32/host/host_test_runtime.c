/* The fixture runs the production C functions with mock queues and a codec. */

#define _POSIX_C_SOURCE 200809L
#include "itofs_service.h"
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#define pdTRUE 1
#define portMAX_DELAY -1
#define pdMS_TO_TICKS(n) (n)
#define I2S_SLICE 480
#define TAIL_SAMPLES 120
#define MALLOC_CAP_INTERNAL 0
#define MALLOC_CAP_DMA 0
typedef int esp_err_t;
typedef struct {
  int16_t *pcm;
  int n;
  uint32_t job;
} buf_t;
typedef struct {
  pthread_mutex_t lock;
  pthread_cond_t cond;
  int head, tail, count;
  size_t item_size;
  unsigned char items[32][sizeof(buf_t)];
} queue;
#define QUEUE_INIT(type)                                                       \
  {.lock = PTHREAD_MUTEX_INITIALIZER,                                          \
   .cond = PTHREAD_COND_INITIALIZER,                                           \
   .item_size = sizeof(type)}
typedef struct {
  int mode;
  int64_t t_arrive;
  uint32_t job;
} fejob_t;
static queue full = QUEUE_INIT(buf_t), freeq = QUEUE_INIT(buf_t),
             done = QUEUE_INIT(buf_t), frontend = QUEUE_INIT(fejob_t);
static queue *s_full_q = &full, *s_free_q = &freeq, *s_done_q = &done,
             *s_fe_q = &frontend;
static atomic_uint s_park_epoch[3], s_stop_sequence;
static void guard_wdt_feed(void) {}
static atomic_uint s_fe_job;
static atomic_int s_fe_up = 1;
static char text_storage[4096], *s_fe_text = text_storage;
static const char phrases_start[1] = {0}, phrases_end[1] = {0};
static int64_t esp_timer_get_time(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec * 1000000LL + t.tv_nsec / 1000;
}
static struct timespec deadline(int ms) {
  struct timespec t;
  clock_gettime(CLOCK_REALTIME, &t);
  t.tv_sec += ms / 1000;
  t.tv_nsec += (ms % 1000) * 1000000L;
  if (t.tv_nsec >= 1000000000) {
    t.tv_sec++;
    t.tv_nsec -= 1000000000;
  }
  return t;
}
static int xQueueReceive(queue *q, void *p, int ms) {
  pthread_mutex_lock(&q->lock);
  struct timespec until = deadline(ms < 0 ? 10000 : ms);
  while (!q->count) {
    if (ms == 0) {
      pthread_mutex_unlock(&q->lock);
      return 0;
    }
    int r = pthread_cond_timedwait(&q->cond, &q->lock, &until);
    if (r == ETIMEDOUT) {
      pthread_mutex_unlock(&q->lock);
      return 0;
    }
  }
  memcpy(p, &q->items[q->head], q->item_size);
  q->head = (q->head + 1) % 32;
  q->count--;
  pthread_cond_broadcast(&q->cond);
  pthread_mutex_unlock(&q->lock);
  return 1;
}
static int xQueueSend(queue *q, const void *p, int ms) {
  (void)ms;
  pthread_mutex_lock(&q->lock);
  assert(q->count < 32);
  memcpy(&q->items[q->tail], p, q->item_size);
  q->tail = (q->tail + 1) % 32;
  q->count++;
  pthread_cond_broadcast(&q->cond);
  pthread_mutex_unlock(&q->lock);
  return 1;
}
static void vTaskDelay(int ms) {
  struct timespec t = {ms / 1000, (ms % 1000) * 1000000L};
  nanosleep(&t, NULL);
}
static void vTaskDelete(void *p) {
  (void)p;
  pthread_exit(NULL);
}
static void *heap_caps_malloc(size_t n, int caps) {
  (void)caps;
  return malloc(n);
}
static const char *esp_err_to_name(int e) {
  (void)e;
  return "mock";
}
static double ms(int64_t us) { return us / 1000.0; }
static atomic_uint s_job_generation = 1;
static atomic_int s_cancel, s_playing, s_speaking, s_fe_abort;
static int s_sr = 24000, s_underruns, s_delay_override_ms;
static int64_t s_cancel_t, s_utt_t0, s_cur_delay_us, s_first_i2s_submit_us;
static pthread_mutex_t mock_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t mock_cond = PTHREAD_COND_INITIALIZER;
static int writes, flushes, starts, stops, unmuted, write_hold, write_entered,
    drain_hold, drain_entered;
static int tags[64];
static esp_err_t mock_write(void *u, const int16_t *p, size_t n) {
  (void)u;
  (void)n;
  pthread_mutex_lock(&mock_lock);
  tags[writes++] = p[0];
  write_entered = 1;
  pthread_cond_broadcast(&mock_cond);
  while (write_hold)
    pthread_cond_wait(&mock_cond, &mock_lock);
  pthread_mutex_unlock(&mock_lock);
  return 0;
}
static esp_err_t mock_drain(void *u) {
  (void)u;
  pthread_mutex_lock(&mock_lock);
  drain_entered = 1;
  pthread_cond_broadcast(&mock_cond);
  while (drain_hold)
    pthread_cond_wait(&mock_cond, &mock_lock);
  pthread_mutex_unlock(&mock_lock);
  return 0;
}
static esp_err_t mock_flush(void *u) {
  (void)u;
  pthread_mutex_lock(&mock_lock);
  flushes++;
  pthread_cond_broadcast(&mock_cond);
  pthread_mutex_unlock(&mock_lock);
  return 0;
}
static esp_err_t mock_mute(void *u, bool muted) {
  (void)u;
  pthread_mutex_lock(&mock_lock);
  if (!muted)
    unmuted = 1;
  pthread_cond_broadcast(&mock_cond);
  pthread_mutex_unlock(&mock_lock);
  return 0;
}
static void mock_playing(void *u, bool playing) {
  (void)u;
  pthread_mutex_lock(&mock_lock);
  if (playing)
    starts++;
  else
    stops++;
  pthread_cond_broadcast(&mock_cond);
  pthread_mutex_unlock(&mock_lock);
}
static itofs_service_config_t s_audio = {.write = mock_write,
                                         .drain = mock_drain,
                                         .flush = mock_flush,
                                         .mute = mock_mute,
                                         .playing = mock_playing};
static void audio_mute(int);
#define CODEC_MUTE(m) audio_mute(m)

#include "production_functions.inc"

static int16_t pcm[960];
static void wait_for(int *p) {
  pthread_mutex_lock(&mock_lock);
  struct timespec end = deadline(1000);
  while (!*p)
    assert(pthread_cond_timedwait(&mock_cond, &mock_lock, &end) != ETIMEDOUT);
  pthread_mutex_unlock(&mock_lock);
}
static void reset(void) {
  pthread_mutex_lock(&mock_lock);
  writes = flushes = starts = stops = unmuted = write_hold = write_entered =
      drain_hold = drain_entered = 0;
  pthread_mutex_unlock(&mock_lock);
  s_cancel = 0;
  s_speaking = 1;
  s_playing = 0;
  s_first_i2s_submit_us = 0;
  s_utt_t0 = esp_timer_get_time();
  s_cur_delay_us = 0;
  s_delay_override_ms = 0;
}
static void put(uint32_t job, int n, int tag) {
  if (n)
    for (int i = 0; i < 960; i++)
      pcm[i] = (int16_t)tag;
  buf_t b = {n ? pcm : NULL, n, job};
  xQueueSend(s_full_q, &b, -1);
}
static void finish(uint32_t job) {
  put(job, 0, 0);
  buf_t b;
  assert(xQueueReceive(s_done_q, &b, 1000));
  s_speaking = 0;
  assert(!s_playing);
}
static void *player(void *p) {
  play_task(p);
  return NULL;
}
static void test_frontend_owner(void) {
  assert(fe_submit("old", 0) == 0);
  uint32_t old = atomic_load(&s_job_generation);
  cancel_job();
  fe_release(old);
  assert(fe_submit("new", 0) == 0);
  fe_release(old);
  fe_release(old);
  assert(fe_busy());
  assert(fe_submit("overwrite", 0) == -1);
  assert(strcmp(s_fe_text, "new") == 0);
  fe_release(atomic_load(&s_job_generation));
  assert(!fe_busy());
  puts("PASS stale frontend producer/end marker cannot release or overwrite a "
       "new job");
}
int main(void) {
  test_frontend_owner();
  pthread_t task;
  assert(!pthread_create(&task, NULL, player, NULL));
  uint32_t job;
  reset();
  job = atomic_load(&s_job_generation);
  s_delay_override_ms = 2000;
  put(job, 480, 1);
  wait_for(&unmuted);
  cancel_job();
  finish(job);
  assert(writes == 0 && flushes == 1 && starts == 0 && stops == 1);
  puts("PASS cancel during pre-roll");
  reset();
  job = atomic_load(&s_job_generation);
  write_hold = 1;
  put(job, 960, 2);
  wait_for(&write_entered);
  cancel_job();
  pthread_mutex_lock(&mock_lock);
  write_hold = 0;
  pthread_cond_broadcast(&mock_cond);
  pthread_mutex_unlock(&mock_lock);
  finish(job);
  assert(writes == 1 && flushes == 1 && starts == 1 && stops == 1);
  puts("PASS cancel during in-flight write prevents the next slice");
  reset();
  job = atomic_load(&s_job_generation);
  put(job, 480, 3);
  wait_for(&write_entered);
  buf_t returned;
  while (xQueueReceive(s_free_q, &returned, 0)) {
  }
  cancel_job();
  wait_for(&flushes);
  put(job, 480, 3);
  finish(job);
  assert(writes == 1 && flushes == 1);
  puts("PASS cancel while starved flushes without waiting for synthesis");
  reset();
  job = atomic_load(&s_job_generation);
  drain_hold = 1;
  put(job, 480, 4);
  put(job, 0, 0);
  wait_for(&drain_entered);
  cancel_job();
  pthread_mutex_lock(&mock_lock);
  drain_hold = 0;
  pthread_cond_broadcast(&mock_cond);
  pthread_mutex_unlock(&mock_lock);
  buf_t b;
  assert(xQueueReceive(s_done_q, &b, 1000));
  s_speaking = 0;
  assert(flushes == 1 && stops == 1);
  puts("PASS cancel during final drain closes playback");
  reset();
  job = atomic_load(&s_job_generation);
  s_speaking = 0;
  cancel_job();
  put(job, 480, 5);
  finish(job);
  assert(writes == 0 && starts == 0);
  puts("PASS queued stale PCM is discarded before output");
  reset();
  job = atomic_load(&s_job_generation);
  put(job, 480, 6);
  finish(job);
  assert(writes >= 1 && tags[0] == 6 && flushes == 0 && starts == 1 &&
         stops == 1);
  puts("PASS next job plays after cancellation without stale PCM");
  return 0;
}
