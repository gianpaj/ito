# Agent Note: Ito inference memory ownership

Status: proposed, host lifecycle and golden reuse tests pass; the reserved-pool
candidate needs integrated device transitions and memory measurements.

## Problem

Half-duplex STT needs inference memory between Ito utterances. Cancel stops
speech but leaves its storage resident. Freeing the early hot reservation risks
losing its contiguous SRAM block. Returning separate PSRAM inference blocks to
TLSF does not guarantee that the weight-copy block can be allocated again.

## Proposal

The embedded service owns two reserved memory ranges: the early internal hot
arena and one 64-byte-aligned PSRAM pool. The pool contains the padded weight
copy, bulk arena and six full-capacity PCM buffers. It is allocated before kernel
and frontend startup and stays allocated across stop/resume. Standalone firmware
keeps its separate heap allocations and optional mapped-flash fallback.

`itofs_service_stop` closes admission, invalidates the active generation,
flushes playback and waits for frontend, synthesis and player checkpoints.
It clears model/context and all derived workspace aliases, resets queues and
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

## Acceptance criteria

Production-function tests cover initial pool allocation failure, retry,
callback failure, timeout ownership, exact exclusive leases, capacity bounds and
100 overwrite/reuse transitions. Real checkpoint threads reject stale epochs.
Actual portable-engine PCM matches after overwriting both workspace ranges.
Device tests must confirm PSRAM-backed weights after every resume, stable
workspace addresses/sizes and idle heap/largest blocks, original face, volume,
cancellation and golden PCM through 100 transitions. Measure control-task stack
high-water use during start and resume.

## Risks

Initial calibration and explicit long diagnostics can delay parking. Callbacks
must finish cooperatively. Allocation seams do not prove every IDF or espeak
internal failure. Partial required frontend/kernel allocations are reused on
retry; exhaustive espeak internal OOM teardown is outside this bounded stage.
Static external BSS and retained services remain outside the borrowed pool.

A 4,096-byte USB control task overflowed in model layout during resume. Sizing
runs on the caller despite synthesis having its own worker stack. Use at least
8,192 bytes of internal caller stack and measure remaining headroom. The
8,192-byte device candidate reported 2,936 bytes remaining during resume.
Host mocks and portable-engine tests do not reproduce ESP32 caller-stack limits.
Flash-calling control tasks must not use PSRAM stacks.

Parked workers feed the application watchdog callback. An actual recognizer
integration must gate that callback by active phase/owner so a parked TTS worker
cannot hide stalled STT work. A recognizer watchdog handoff is not implemented.
