# Oido v2b memory budget

At upstream revision `c8d60325ba8bffd4bad65a9ac63c713ee64d1aae`, flash-backed
v2b weights with greedy decoding require about **1.45 MiB of engine allocations**.
A 10-second, 16 kHz mono PCM16 capture ring adds 320,000 bytes. Budget about
**2.2-2.5 MiB of available PSRAM** for the engine, ring, a separate 10-second
utterance buffer and allocator headroom. Reserve 3 MiB when practical.
These are host-derived integration estimates, not an ESP32 minimum-memory test.
No local LLM or speech language model is included.

| Requested allocation | Bytes |
|---|---:|
| Engine peak, all allocation kinds combined | 1,520,880 |
| Engine persistent streaming state | 1,475,824 |
| Peak plus 10-second capture ring | 1,840,880 |
| Peak plus ring and separate 10-second utterance buffer | 2,160,880 |
| Remaining tracked allocations after freeing stream and model | 0 |

The model is 5,931,424 bytes, SHA256
`9e8b40913f532fb44b716a1f882f38b3b21e220713e417899aba32ace8c35066`.
Its image is treated as flash-mapped storage and excluded from RAM totals.
Weight relocation with a zero-byte budget copies zero bytes. Streaming attention,
convolution and positional caches remain allocated; "no caching" here means
**no acoustic weights copied to PSRAM**, not removal of streaming state.

## Reproduce

With an existing checkout of the pinned Oido revision and its model:

```sh
python3 oido-memory-probe.py /path/to/oido --output measured.json
```

[oido-memory-probe.py](oido-memory-probe.py) builds the upstream host engine,
hooks its allocator, loads v2b, creates default chunk-8/left-64 streaming state
without an LM, feeds 10 seconds of silence, finishes, then frees both objects.
[oido-memory-measured.json](oido-memory-measured.json) records build flags,
compiler, model hash and allocation totals. Feeding the stream does not increase
the initialization peak. Freeing it returns the tracked allocation count to zero.
Only these source/report files belong in Git; model weights are excluded.

The host uses 64-bit pointers; ESP32 uses 32-bit pointers. Allocation requests
exclude allocator metadata, alignment padding, tasks, DMA, static BSS and host
runtime memory. Hot allocations total 211,460 bytes. The upstream firmware
prefers internal SRAM for them, then falls back to PSRAM when headroom is low.
StackChan's measured 13 KB of warm internal free memory still requires a separate
I2S receive/DMA/task budget. Available PSRAM alone does not establish that it fits.

## Upstream board evidence

The [flash-weight benchmark configuration](https://github.com/lokutor-ai/oido/blob/c8d60325ba8bffd4bad65a9ac63c713ee64d1aae/esp32/bench/queue11.sh)
uses an LM with beam 2/top-k 3. Its [v2b results](https://github.com/lokutor-ai/oido/blob/c8d60325ba8bffd4bad65a9ac63c713ee64d1aae/esp32/bench/r_nops_b3.json)
report minimum free PSRAM of **5,059,880 bytes** and minimum free internal RAM of
**75,888 bytes**. Those are remaining heap capacities, not required memory.
The feed-plus-finish times total 78.859956 seconds for 120.19 seconds of audio,
a weighted streaming RTF of 0.65613. The JSON's near-zero batch `rtf_mean` field
is not its streaming RTF. This is a file benchmark, not a measured microphone run.

The [firmware allocation policy](https://github.com/lokutor-ai/oido/blob/c8d60325ba8bffd4bad65a9ac63c713ee64d1aae/esp32/firmware/main/main.c#L89-L178)
copies LM matrices to RAM even when acoustic-weight relocation is disabled.
The host probe removes both the LM and decoder. The upstream board uses octal
PSRAM; StackChan uses quad PSRAM. These results do not predict StackChan speed.
The [microphone code](https://github.com/lokutor-ai/oido/blob/c8d60325ba8bffd4bad65a9ac63c713ee64d1aae/esp32/firmware/main/mic.c#L18-L89)
keeps an eight-second capture ring and a separate 20-second utterance buffer,
896,001 bytes combined. A ten-second ring alone therefore understates the
unmodified microphone path. A rough 3 MiB allowance is useful headroom, not a
measured no-LM engine requirement.
