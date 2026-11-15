/* Portable production engine rebuild after another owner overwrites both retained pools. */
#include "itofs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void *aligned(size_t bytes)
{
    void *p=NULL;
    assert(posix_memalign(&p,64,bytes)==0);
    return p;
}
static size_t rounded(size_t bytes) { return (bytes+63)&~(size_t)63; }
static void read_into(const char *path,void *blob,size_t bytes)
{
    FILE *file=fopen(path,"rb");assert(file);
    assert(fread(blob,1,bytes,file)==bytes);assert(fgetc(file)==EOF);
    assert(fclose(file)==0);
}
int main(int argc,char **argv)
{
    if (argc!=2) { fprintf(stderr,"usage: %s <model-with-8-bit-selftest.bin>\n",argv[0]);return 2; }
    FILE *file=fopen(argv[1],"rb");assert(file);
    assert(fseek(file,0,SEEK_END)==0);long length=ftell(file);assert(length>0);
    assert(fclose(file)==0);
    const size_t blob_bytes=(size_t)length;
    void *initial_blob=aligned(blob_bytes);
    read_into(argv[1],initial_blob,blob_bytes);
    itofs_model_t model;itofs_ctx_t context;
    assert(itofs_model_init(&model,initial_blob,blob_bytes)==0);
    const itofs_limits_t limits={400,32,8,0};
    size_t hot_bytes,bulk_bytes;
    itofs_arena_bytes(&model,&limits,&hot_bytes,&bulk_bytes);
    const size_t pcm_bytes=(size_t)32*model.hop*sizeof(int16_t);
    const size_t bulk_offset=rounded(blob_bytes+64);
    const size_t pcm_offset=bulk_offset+((bulk_bytes+15)&~(size_t)15);
    const size_t pcm_stride=(pcm_bytes+15)&~(size_t)15;
    const size_t psram_bytes=rounded(pcm_offset+6*pcm_stride);
    void *hot=aligned(hot_bytes), *psram=aligned(psram_bytes);
    void *bulk=(unsigned char *)psram+bulk_offset;
    free(initial_blob);memset(&model,0,sizeof model);
    uint32_t baseline_hash=0;size_t baseline_samples=0;
    for (int cycle=0;cycle<4;cycle++) {
        memset(hot,0xa5,hot_bytes);memset(psram,0xa5,psram_bytes);
        read_into(argv[1],psram,blob_bytes);
        assert(itofs_model_init(&model,psram,blob_bytes)==0);
        const int32_t *reference=NULL;size_t record_bytes=0;int dtype=0;
        assert(itofs_blob_find(psram,blob_bytes,"selftest",(const void **)&reference,&record_bytes,&dtype)==0);
        assert(dtype==2 && record_bytes>=7*sizeof(*reference));
        assert(reference[0]==0x32525453 && reference[6]==8);
        assert(reference[1]>0 && record_bytes>=(size_t)(7+reference[1])*sizeof(*reference));
        assert(itofs_init(&context,&model,&limits,hot,hot_bytes,bulk,bulk_bytes)==0);
        assert(itofs_begin(&context,reference+7,reference[1],reference[2],(uint32_t)reference[3])>=0);
        uint32_t hash=2166136261u;size_t samples=0;unsigned buffer=5;
        for (;;) {
            int16_t *pcm=(int16_t *)((unsigned char *)psram+pcm_offset+(buffer++%6)*pcm_stride);
            int n=itofs_next_chunk(&context,pcm,32*model.hop);assert(n>=0);
            if (!n) break;
            samples+=(size_t)n;
            for (int i=0;i<n;i++) { hash^=(uint16_t)pcm[i];hash*=16777619u; }
        }
        assert(samples==(size_t)reference[4] && hash==(uint32_t)reference[5]);
        if (!cycle) { baseline_hash=hash;baseline_samples=samples; }
        assert(hash==baseline_hash && samples==baseline_samples);
        printf("PASS real engine pool cycle %d: %zu samples, PCM fnv32 %08x, hot %zu / PSRAM %zu bytes\n",
               cycle,samples,hash,hot_bytes,psram_bytes);
        memset(&context,0,sizeof context);memset(&model,0,sizeof model);
    }
    free(psram);free(hot);
    return 0;
}
