# Agent Note: Ito inference memory ownership

Status: proposed, implementation has host coverage; integrated device transitions
and memory measurements are pending.

## Problem

Half-duplex STT needs inference memory between Ito utterances. Cancel stops
speech but does not release the resident weight copy, bulk arena or PCM pool.
Freeing the early hot reservation would risk losing its contiguous SRAM block.

## Proposal

The embedded service has a parked inference state. `itofs_service_stop` closes
command admission, invalidates the active generation, flushes playback and waits
for frontend, synthesis and player checkpoints. It then releases inference
storage. The standalone firmware retains its continuous service behavior.

The stop state and epoch share one atomic word. Workers acknowledge its exact
odd value. Resume changes that value to even with a compare-and-exchange after
allocation and initialization succeed. A departing worker's acknowledgement
cannot authorize another stop; a concurrent stop prevents resume from opening
admission. A timeout keeps admission closed and memory owned until stop succeeds.

The synthesis checkpoint drains kernel prefetch and clears helper descriptors.
A DMA error makes completion uncertain. It latches `ESP_FAIL`, retains inference
storage and requires reboot. No hot borrowing or resume follows that error.

The normal int4 profile releases these PSRAM allocations:

| Allocation | Bytes |
|---|---:|
| Weight copy and margin | 3,196,160 |
| Bulk arena | 1,579,920 |
| Six PCM buffers | 115,200 |
| Total | 4,891,280 |
| Optional quiet-text diagnostic scratch | 576,000 |

Task stacks, queues, frontend state and its PSRAM stack remain resident. Kernel
tiles, GDMA channels and the helper task remain resident. These are retained
costs, not reclaimed budget. Required partial frontend/kernel allocations are
reused on retry; this is not an exhaustive espeak internal OOM teardown.

The 239,948-byte hot arena stays reserved in internal SRAM. After successful
stop, `borrow_hot` grants exclusive use until `return_hot` receives the same
pointer. The application must not free it or retain derived pointers afterward.
Resume rejects an outstanding borrow and reinitializes the engine before use.
Codec open/volume and guard records persist; calibration remains tied to the
same fixed voice, precision and scheduling profile.

Persistent codec initialization precedes the phase-owned weight copy and bulk
arena. Keeping retained codec objects outside that group lets released inference
blocks coalesce. Weight-copy admission uses total free PSRAM, then attempts the
aligned allocation; total capacity alone does not establish TLSF fit. A device
resume failed to reacquire the 3,196,160-byte copy with 7,979,556 bytes free and
a 3,145,728-byte reported largest block. The allocation-order candidate needs
device confirmation before claiming repeatable PSRAM-backed resume.

## Alternatives considered

Full task, frontend and GDMA teardown would recover more memory, but needs a
separate espeak-global cleanup audit and safe task-stack reclamation. Use it only
if the retained costs fail the measured STT fit gate. Releasing the hot arena to
the general heap does not preserve contiguous allocation. Keeping both inference
arenas resident does not provide the intended phase memory budget.

## Acceptance criteria

Production-function host tests cover partial inference allocation failure,
retry, callback failure, timeout ownership, exclusive borrowing and 100 memory
reuse transitions. Real checkpoint threads must reject stale epochs. Golden
PCM must match after overwriting and reinitializing the hot arena. Device tests
must confirm the same idle heap/largest blocks, original face, cancellation,
volume and deterministic PCM through 100 transitions.
Measure the control task's stack high-water use during start and resume.

## Risks

Initial calibration and explicit long diagnostics can delay worker parking.
Application callbacks must finish cooperatively. Host allocation seams do not
prove every IDF allocation or espeak internal failure. Static external BSS,
retained frontend memory and retained SRAM tasks/tiles still count in STT fit.

The first device stop/borrow probe succeeded, but resume from a 4,096-byte USB
control task overflowed its stack in model layout. Sizing runs on the caller,
even though synthesis uses its own worker stack. Use at least 8,192 bytes of
internal caller stack for this profile and measure the remaining headroom.
The startup baseline uses an 8,192-byte main stack. Host mocks and portable
engine tests do not reproduce ESP32 caller stack limits; they did not establish
that a 4 KiB control task could resume safely. Keep flash-calling control tasks
off PSRAM stacks.
