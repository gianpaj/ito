# StackChan native Ito speech

Status: the native USB text-to-speech demo is implemented and installed.
The user confirms clear speech. Five repeated paragraphs produce 980 seconds
of speech with zero underruns, no resets and unchanged memory after warm-up.
Compute RTF is 1.000906, so the firmware retains its DEGRADED warning.

The deadline scope is native speech from USB text. Conversation, extra reboot
cycles and the full factory-restore rehearsal are deferred. This delivers the
requested demo without claiming the original strict streaming gate passes.

## Decisions

- Use StackChan's quad PSRAM at 80 MHz and QIO runtime flash at 80 MHz. The
  boot-image header stays DIO, matching the factory bootloader.
- Keep row split and its failed-full latch. A full-split test passed, but the
  next boot detected a mismatch. The cause is unknown. Do not force full split
  or clear its failure counters to improve speed.
- Use 32-frame chunks and a full first chunk. The hot arena occupies 239,948
  bytes of internal SRAM; the bulk arena uses 1,579,920 bytes of PSRAM. The
  host profile rejects 40-frame chunks because their hot arena exceeds the
  measured largest internal block. Do not move the hot arena to PSRAM.
- Keep the main model at `0x200000` and the approved female int4 fallback at
  `0x680000`. Calibration selects int4. The unapproved female light variant is
  absent. No model architecture or arithmetic changes are needed for the port.
- Select the measured gdma+prefetch mode at StackChan startup. It is the
  fastest of all four modes on both models. Skip the full boot benchmark and
  retain calibration and self-tests. `bench` runs diagnostics manually; if the
  staging mode is unavailable, startup benchmarks the available modes. This
  avoids calibration-cache state for the fixed device profile.
- Pin the StackChan text frontend to core 1 and keep synthesis on core 0. The
  long speaker paragraph improves from RTF 1.00194 to 1.00098. Both placements
  match host PCM. Other boards keep frontend core 0.
- Use the AW88298 codec control interface from esp_codec_dev 1.5.4. Its
  high-level mute and volume methods discard driver errors, and its data
  interface would reconfigure Ito's I2S channel. The control interface checks
  errors while Ito owns the existing audio path.
- Hold amplifier reset during board setup. Read back motor power and power
  rails before playback. Keep microphone power, motor power and backlight off.
- Use GPIO0 as MCLK and omit the GPIO0 demo-button task. I2S uses BCLK 34,
  WS 33 and DOUT 13, at 24 kHz with mono duplicated into two 16-bit slots.
- Set volume 35 after the user reports that 25 is too quiet. Volume zero stays
  muted across utterances. The amplifier is muted while idle and held in reset
  after a codec error. Failed or short I2S writes cancel playback.
- Store one brief greeting in `main/stackchan_phrases.txt`. Preserve the generic
  board phrase list. The greeting runs after self-tests and calibration.

## Evidence

The user confirms clear speech, still motors and an unlit screen. Schematics
and source references are listed in `esp32/STACKCHAN.md`. Power readbacks
confirm AXP2101 `0x34`, AW9523 `0x58` and base PY32 `0x6f`, version `0x41`.

The main self-test matches host FNV32 `023bd6b1`; int4 matches `363d7d98`.
Both produce 134,100 samples. Main 8-bit and 16-bit host tests pass. Main and
int4 8-bit ASan/UBSan runs pass. The frontend matches 2,337 single-utterance
and 169 streaming golden cases. Existing scheduler and split tests pass.

All 26 utterances of the 196-second paragraph match host token and PCM hashes.
The core-1 comparison measures silent RTF 0.998 and speaker RTF 1.001. Twenty
spoken prompts on core 0 measure aggregate RTF 0.999 with zero underruns.
Three core-0 speaker paragraphs each measure about 1.002 with zero underruns.
Five core-1 speaker paragraphs measure aggregate RTF 1.000906 across
980 seconds of generated speech. There are zero underruns or I2S errors and
no resets. Timing margin remains small; `DEGRADED` stays visible.

Free internal SRAM stays near 32 KB after warm-up, with a measured minimum of
8 KB. The silent PCM scratch ring accounts for about 576 KB of persistent
PSRAM allocation. Compare memory after the same buffers have warmed up.

The serial monitor passes pseudo-terminal checks for batched input, split
UTF-8, an EOF-terminated command, private logs and metadata. `TIMING` records
first PCM separately from the player's first successful I2S API submission.
The latter excludes DMA and acoustic latency. Supplied prebuilt images remain
unchanged; the default DevKit and QEMU configurations build independently.

## Artifacts and execution

Use the [backup record](../../proposed/hardware/2026-11-14-stackchan-backup-preflight.md) for the private
original flash, checksum and restore runbook. The full factory restore rehearsal
is pending. Preserve Ito's NVS safety counters when returning from that test.

Builds, model checks, reference audio and measurements are under
`esp32/logs/stackchan/20261114T184935.713345Z/`. Metadata records hashes of the
images, configurations and models. The installed merged image SHA-256 is
`386bb5b737b3f3f0b467118abf1dd5a154aa0bde2b8eddac9bbae5bc0d71ca71`.

The serial monitor owns the port while running and prints its private session
folder. Close it before another serial tool opens the device. Opening native
USB serial can reset the chip. Startup reaches READY in 25.9 seconds and
finishes the stored greeting in 29.3 seconds, measured from serial open.
Wait for the greeting to finish before sending text.

The fast-boot image passes both model self-tests and calibrates both models.
USB greeting playback has zero underruns, and the number-sentence token and
PCM hashes match the host. Its logs are under
`esp32/logs/stackchan/20261114T205347.304975Z/`. DevKit and QEMU builds pass.
The 980-second stability result covers the retained synthesis profile.

The full backup is verified. Recovery rehearsal and additional boot-cycle
checks remain deferred. Retain the original backup and do not force full split
or disable watchdog and brownout checks. The larger plan keeps the strict
streaming gate for future work.
