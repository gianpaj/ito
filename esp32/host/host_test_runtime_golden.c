/* Portable production engine rebuild after another owner overwrites retained hot SRAM. */
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
static void *read_blob(const char *path,size_t *bytes)
{
    FILE *file=fopen(path,"rb");assert(file);
    assert(fseek(file,0,SEEK_END)==0);long length=ftell(file);assert(length>0);
    rewind(file);*bytes=(size_t)length;
    void *blob=aligned(*bytes);
    assert(fread(blob,1,*bytes,file)==*bytes);assert(fclose(file)==0);
    return blob;
}
int main(int argc,char **argv)
{
    if (argc!=2) { fprintf(stderr,"usage: %s <model-with-8-bit-selftest.bin>\n",argv[0]);return 2; }
    void *hot=NULL,*bulk=NULL,*blob=NULL;
    size_t hot_bytes=0,bulk_bytes=0,blob_bytes=0;
    uintptr_t old_blob=0,old_bulk=0;
    itofs_model_t model;
    itofs_ctx_t context;
    uint32_t baseline_hash=0;size_t baseline_samples=0;
    for (int cycle=0;cycle<4;cycle++) {
        blob=read_blob(argv[1],&blob_bytes);
        assert((uintptr_t)blob!=old_blob);
        assert(itofs_model_init(&model,blob,blob_bytes)==0);
        const int32_t *reference=NULL;size_t record_bytes=0;int dtype=0;
        assert(itofs_blob_find(blob,blob_bytes,"selftest",(const void **)&reference,&record_bytes,&dtype)==0);
        assert(dtype==2 && record_bytes>=7*sizeof(*reference));
        assert(reference[0]==0x32525453 && reference[6]==8);
        assert(reference[1]>0 && record_bytes>=(size_t)(7+reference[1])*sizeof(*reference));
        itofs_limits_t limits={400,32,8,0};
        size_t next_hot,next_bulk;
        itofs_arena_bytes(&model,&limits,&next_hot,&next_bulk);
        if (!hot) { hot_bytes=next_hot;hot=aligned(hot_bytes); }
        assert(hot_bytes==next_hot);
        bulk_bytes=next_bulk;bulk=aligned(bulk_bytes);
        assert((uintptr_t)bulk!=old_bulk);
        memset(bulk,0xdd,bulk_bytes);
        assert(itofs_init(&context,&model,&limits,hot,hot_bytes,bulk,bulk_bytes)==0);
        assert(itofs_begin(&context,reference+7,reference[1],reference[2],(uint32_t)reference[3])>=0);
        int16_t *pcm=aligned((size_t)32*model.hop*sizeof(*pcm));
        uint32_t hash=2166136261u;size_t samples=0;
        for (;;) {
            int n=itofs_next_chunk(&context,pcm,32*model.hop);assert(n>=0);
            if (!n) break;
            samples+=(size_t)n;
            for (int i=0;i<n;i++) { hash^=(uint16_t)pcm[i];hash*=16777619u; }
        }
        free(pcm);
        assert(samples==(size_t)reference[4] && hash==(uint32_t)reference[5]);
        if (!cycle) { baseline_hash=hash;baseline_samples=samples; }
        assert(hash==baseline_hash && samples==baseline_samples);
        printf("PASS real engine cycle %d: %zu samples, PCM fnv32 %08x, hot %zu bytes\n",cycle,samples,hash,hot_bytes);
        old_bulk=(uintptr_t)bulk;old_blob=(uintptr_t)blob;
        free(bulk);free(blob);bulk=blob=NULL;
        memset(&context,0,sizeof context);memset(&model,0,sizeof model);
        memset(hot,0xa5,hot_bytes);
    }
    free(hot);
    return 0;
}
