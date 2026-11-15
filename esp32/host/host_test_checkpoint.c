/* Real worker checkpoint and epoch predicate with a controlled POSIX scheduler. */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
#define PARK_FE 1u
#define PARK_SYNTH 2u
#define PARK_PLAY 4u
#define pdMS_TO_TICKS(n) (n)
static atomic_uint s_stop_sequence, s_park_epoch[3];
static unsigned s_workers = PARK_FE | PARK_SYNTH | PARK_PLAY;
static pthread_mutex_t gate = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static unsigned sleeping[3], permits[3];
static _Thread_local unsigned worker_index;
static atomic_uint watchdog_feeds;
static void guard_wdt_feed(void) { atomic_fetch_add(&watchdog_feeds,1); }
static void vTaskDelay(int ticks) {
    assert(ticks==10);
    pthread_mutex_lock(&gate);
    sleeping[worker_index]++;
    pthread_cond_broadcast(&changed);
    while (!permits[worker_index]) pthread_cond_wait(&changed,&gate);
    permits[worker_index]--;
    pthread_mutex_unlock(&gate);
}
#include "production_functions.inc"
static void *worker(void *arg) {
    worker_index=(unsigned)(uintptr_t)arg;
    service_checkpoint(1u<<worker_index);
    return NULL;
}
static void wait_sleeping(unsigned count) {
    struct timespec deadline;
    clock_gettime(CLOCK_REALTIME,&deadline);deadline.tv_sec+=2;
    pthread_mutex_lock(&gate);
    for (unsigned i=0;i<3;i++)
        while (sleeping[i]<count)
            assert(pthread_cond_timedwait(&changed,&gate,&deadline)==0);
    pthread_mutex_unlock(&gate);
}
static void release_workers(void) {
    pthread_mutex_lock(&gate);
    for (unsigned i=0;i<3;i++) permits[i]++;
    pthread_cond_broadcast(&changed);
    pthread_mutex_unlock(&gate);
}
int main(void) {
    request_stop();
    pthread_t tasks[3];
    for (unsigned i=0;i<3;i++) assert(!pthread_create(&tasks[i],NULL,worker,(void *)(uintptr_t)i));
    wait_sleeping(1);assert(workers_parked());
    for (unsigned cycle=1;cycle<=100;cycle++) {
        /* Resume and stop before the parked workers can consume the resume. */
        atomic_fetch_and(&s_stop_sequence,~1u);
        request_stop();
        assert(!workers_parked());
        release_workers();wait_sleeping(cycle+1);
        assert(workers_parked());
    }
    /* A departing checkpoint's retained ACK cannot authorize the next stop. */
    atomic_fetch_and(&s_stop_sequence,~1u);release_workers();
    for (unsigned i=0;i<3;i++) assert(!pthread_join(tasks[i],NULL));
    request_stop();
    assert(!workers_parked());
    assert(atomic_load(&watchdog_feeds)>=303);
    puts("PASS real worker checkpoints reject stale epochs across 100 rapid resume/stop cycles and worker departure");
    return 0;
}
