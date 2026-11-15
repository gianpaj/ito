# Agent Note: Ito inference memory ownership

Status: implemented — Device and host workspace-reuse checks pass.

## Problem

Half-duplex STT needs inference memory between Ito utterances. Cancel stops
speech but leaves its storage resident. Freeing the early hot reservation risks
losing its contiguous SRAM block. Returning separate PSRAM inference blocks to
TLSF does not guarantee that the weight-copy block can be allocated again.

## Decision

The embedded service owns two reserved memory ranges: the early internal hot
arena and one 64-byte-aligned PSRAM pool. The pool contains the padded weight
copy, bulk arena and six full-capacity PCM buffers. It is allocated before kernel
and frontend startup and stays allocated across stop/resume. Standalone firmware
keeps its separate heap allocations and optional mapped-flash fallback.

`itofs_service_stop` closes admission, invalidates the active generation,
flushes playback and waits for frontend, synthesis and player checkpoints.
It clears model/context and active workspace aliases, resets queues and
frees optional quiet-text scratch. It does not return either workspace to the
heap. Task stacks, queues, frontend state/stack, kernel tiles, GDMA channels and
the helper task remain resident and count in the phase budget.

The stop state and epoch share one atomic word. Workers acknowledge its exact
odd value. Resume changes that value to even with compare-and-exchange after
initialization succeeds. A departing acknowledgement cannot authorize another
stop; a concurrent stop prevents resume from opening admission. Timeout keeps
admission closed and storage owned until stop succeeds.

The synthesis checkpoint drains prefetch and clears helper descriptors. A DMA
error makes completion uncertain. It latches `ESP_FAIL`, prevents borrowing and
resume, and requires reboot. Ownership remains with Ito.

The native 32-frame female int4 PSRAM workspace has this layout:

| Region | Bytes |
|---|---:|
| Weight copy and 64-byte margin | 3,196,160 |
| Bulk arena, aligned to 16 bytes | 1,579,920 |
| Six 32-frame PCM buffers | 115,200 |
| Final 64-byte allocation padding | 48 |
| Total reserved PSRAM pool | 4,891,328 |

The separate hot reservation is 239,948 bytes. `borrow_memory` grants exclusive
use of both ranges only while workers are stopped. `return_memory` validates
both addresses and lengths. Callers must not free either range or retain
pointers after returning the lease. Resume rejects an outstanding lease, restores
weights from flash, reinitializes model/bulk state and rebuilds PCM descriptors.
It fails closed if its PSRAM workspace is unavailable.

PCM capacity stays at 32 frames even when the active chunk size is smaller.
Stop snapshots the active chunk profile, style and activation precision. Resume
restores them after full-capacity provisioning, so retained calibration uses the
same scheduling profile and a later `chunk 32` command remains within bounds.
Codec open/volume and guard records persist.

## Alternatives considered

Heap reacquisition failed on the device with 7,979,288 bytes free and a reported
largest block of 3,145,728 bytes: the 3,196,160-byte weight copy could not be
allocated. Total-free budgeting and putting persistent audio initialization
before inference did not establish repeatable reacquisition. Reserve one pool
and lend its bytes instead of depending on TLSF coalescing and size classes.

Full frontend, task and GDMA teardown could recover more memory, but needs an
espeak-global cleanup audit and safe stack reclamation. Use it only if measured
retained costs fail the STT fit gate. Keeping both engines' inference storage
resident without phase ownership does not provide the intended shared budget.

## Consequences

The device completes 100 stop/borrow/full-overwrite/return/resume loops. Every
resume restores PSRAM weights without recalibration. Eleven explicit golden
commands yield 33 passing 8-/16-bit cases after reuse. A separate long-diagnostic
test rejects borrowing after three stop timeouts, then stops successfully and
resumes on the same connection. Golden output and spoken greeting pass afterward.

The [measurement report](../../../../results/stackchan/2026-11-15-local-stt-ito/README.md)
records every loop, heap ranges, timing method and failed candidates. Reserved
storage is separate from free heap. Global heap varies by small amounts with
live UI/allocator activity; exact zero global heap drift is not established.
The pool itself is not reallocated across transitions. Actual Oido recognition,
microphone capture and native Tailscale remain independent integration gates.

A 4,096-byte USB control task overflowed during model layout. Sizing runs on
the caller despite synthesis owning a worker. The application uses an 8,192-byte
internal stack; the reserved-pool run leaves at least 3,016 bytes unused. Flash
API calls keep this task's stack in internal RAM. Resume reloads weights in
447-448 ms; the measured probe-return to resume-complete interval is 710-730 ms,
including USB polling. These are costs of lending the inference workspace.

Production-function host tests cover capacity/alignment, failed startup/rebind,
exact leases, timeout/codec/DMA-error ownership and 100 reuse transitions.
Real checkpoint threads reject stale epochs. The portable engine reproduces
PCM after overwriting both ranges under ASan/UBSan. Host ABI sizes differ from
native sizes; allocation seams do not prove every IDF/espeak internal failure.
Partial required frontend/kernel allocations are reused on retry. Full espeak
internal OOM teardown is outside this bounded implementation.

Initial calibration and explicit long diagnostics can delay parking. Callbacks
must finish cooperatively. Parked workers feed the application watchdog callback.
A recognizer integration must gate it by active phase/owner so parked TTS workers
cannot hide stalled STT work. That recognizer watchdog handoff is not implemented.
