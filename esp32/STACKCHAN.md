# Ito on M5Stack StackChan

Status: the phase 1 image is installed. Main and int4 self-tests match the host.
All 26 utterances of a 196-second paragraph match host tokens and PCM. The user confirms clear speech. Sustained playback and restore validation
are in progress; compute RTF remains slightly above the plan's strict limit.

Ito runs the English text frontend and speech model on the ESP32-S3. The Mac
sends text and records USB logs. This target uses the built-in AW88298 speaker,
8 MB quad PSRAM and 16 MB flash. It keeps motor power, microphone power and the
display backlight off. GPIO0 is an audio clock; it has no demo-button task.

## Build

Run commands from the Ito repository root. Use the installed ESP-IDF 5.5.4
environment for firmware work and Ito's Python environment for model downloads.
The weights require account access to <https://huggingface.co/lokutor-ai/ito>.

```sh
source "$HOME/esp/esp-idf/export.sh"
BOARD=stackchan esp32/tools/build_fw.sh
```

The fresh configuration combines `firmware/sdkconfig.defaults` with
`firmware/sdkconfig.stackchan.defaults`. The app and merged image are under
`esp32/firmware/build_stackchan/`. This build does not overwrite supplied
prebuilt files. The defaults select row split, 32-frame chunks and volume 35.
The stored greeting in `main/stackchan_phrases.txt` plays after calibration.
Set `CONFIG_ITOFS_BOOT_TEXT=n` for a silent diagnostic build. The amplifier
stays muted between utterances. Flash runs in QIO at 80 MHz; the boot-image
header remains DIO, matching the factory bootloader.

## Back up before installation

Follow [plan step 1.2](../plans/2026-11-14-stackchan-standalone-ito.md#12-create-and-verify-the-recovery-backup).
Require two matching full 16 MB reads and retain the SHA-256 checksum and
restore instructions privately under `~/stackchan-backups/`. A firmware build
or OTA file does not include the device's complete settings and flash layout.

Use the base USB-C data connection. Esptool's `--before usb_reset` reaches the
ROM bootloader on the tested unit. The
[manufacturer's download-mode procedure](https://docs.m5stack.com/en/StackChan)
is the fallback: hold the bottom RST button for about three seconds, release
when the nearby LED turns green, and wait for it to go off.

## Install the explicit StackChan image

Confirm the connected chip identity, 16 MB capacity, security state and backup
checksum. Close any serial monitor before using esptool. Establish the host
model reference and review the build configuration before the first write.

With the device in download mode, use IDF Python and explicit paths:

```sh
export STACKCHAN_PORT=/dev/cu.usbmodem1101
ESPTOOL_BEFORE=no_reset ESPTOOL_AFTER=no_reset BAUD=460800 \
  esp32/tools/flash.sh "$STACKCHAN_PORT" \
  models/ito_female_esp32s3.bin \
  esp32/firmware/build_stackchan/ito_stackchan_merged.bin
python -m esptool --chip esp32s3 --port "$STACKCHAN_PORT" --baud 460800 \
  --before no_reset --after no_reset write_flash \
  0x680000 models/ito_female_esp32s3_int4.bin
```

Recheck the port after reconnecting USB. The reset environment variables keep
the app stopped between the optional-slot erase and the image write, then
leave it in download mode for a logged reset. No separate full erase is needed.

The merged image starts at `0x0` and includes the bootloader, partition table,
blank NVS region and app. Main weights start at `0x200000`. The flash script
erases `0x680000` through `0xf7ffff` for absent optional weight sets. These writes
replace the original robot firmware and its assets; recovery uses the full
private backup.

## Send text and retain logs

Start the monitor in the IDF shell. It owns the serial port until Ctrl-C.
Opening the native USB serial port can release download mode and start the
app. Use esptool, rather than the monitor, when the chip must stay in the ROM
bootloader. `--reset` requests a reset after the log is open.

```sh
python esp32/tools/stackchan.py monitor --port "$STACKCHAN_PORT" --reset \
  --firmware esp32/firmware/build_stackchan/ito_stackchan_merged.bin \
  --weights models/ito_female_esp32s3_int4.bin
```

Wait for the model self-test, calibration and `READY`. Inspect power and memory
diagnostics before requesting playback. Use `test`, `status`, `stats`, `ids Hello!`,
and `textq Hello!` for the silent checks. Then request a quiet phrase:

```text
volume 35
text Hello! I am StackChan.
cancel
```

`volume 0` keeps the amplifier muted across utterances. Volume uses the codec's
hardware attenuation. Board or codec failures report an error and hold the
amplifier in reset. Ito owns I2S and duplicates mono samples into two 16-bit
slots at 24 kHz. The helper uses the pinned codec driver's control interface;
it does not create an audio task or reconfigure Ito's I2S channel.

The monitor prints its absolute session folder under
`esp32/logs/stackchan/<timestamp>/`. `serial.log` records board output and typed
commands. `metadata.json` records UTC times, device identity, source revision,
tracked-diff hash, tool versions and the supplied image and weight hashes.
Files are private and Git ignores the log directory. `--duration <seconds>`
ends a bounded capture; a disconnected USB cable ends the run with an error.
Runs without a host reader retain no logs.

`TIMING` records first PCM, compute time, RTF, underruns and the planned delay.
`I2S_START` records the first successful PCM submission to the I2S API. It
excludes DMA and acoustic latency. Boot benchmarking and calibration take about
two minutes. Wait for the stored greeting to finish before sending text.

## Validation record

The approved int4 fallback is selected because the main model exceeds RTF 1
in row split. Int4 calibration measures about 0.984. The silent long-paragraph
comparison measures aggregate RTF 0.998. Speaker playback measures about
1.001 with zero underruns. This misses the strict RTF-below-1 gate, and the
firmware reports `DEGRADED`. A full-split check failed on a subsequent boot;
its failure latch stays in place. Do not force full split to improve timing.

| File | Offset | SHA-256 |
| --- | --- | --- |
| `ito_stackchan_merged.bin` | `0x0` | `6338216a1e94e3872846680106654133e0ed54ce0e54d0955e3fb999ad6ff7e6` |
| `ito_female_esp32s3.bin` | `0x200000` | `0266caf56597639b8d1d7d4c26e5f689436bc63fddc8797310b6a877389879f5` |
| `ito_female_esp32s3_int4.bin` | `0x680000` | `155da4f3c58266ab49c0b885caff08d02d72be5635d5bc960c86ed055d529b27` |

The image hash identifies the tested source and configuration. Recheck it after
rebuilding. Logs, host references and image metadata are under
`esp32/logs/stackchan/20261114T184935.713345Z/`. Physical playback logs are under
`esp32/logs/stackchan/20261114T201157.747967Z/`. The firmware source is
commit `8c1edf4`. StackChan pins the text frontend to core 1 and synthesis to
core 0; generic boards retain their default placement.

## Restore

Use the private backup's `RESTORE.md` and verify its checksum before writing.
Restore all 16 MB at `0x0` with `--flash_mode keep --flash_freq keep
--flash_size keep`. Verify the flash before resetting into the original app.
Follow [plan step 1.7](../plans/2026-11-14-stackchan-standalone-ito.md#17-prove-restore-and-leave-ito-installed)
for the restore rehearsal and final Ito installation.

## Hardware references

- [M5Stack StackChan documentation](https://docs.m5stack.com/en/StackChan)
- [CoreS3 schematic](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/490/Sch_M5_CoreS3_v1.0.pdf), sheets 1, 4 and 5
- [StackChan power schematic](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1205/SCH_Power.pdf)
- [M5Unified AXP2101 register definitions](https://github.com/m5stack/M5Unified/blob/master/src/utility/power/AXP2101_Class.inl)
- [Espressif esp_codec_dev 1.5.4](https://components.espressif.com/components/espressif/esp_codec_dev/versions/1.5.4)

The PY32 protocol follows M5Stack's MIT-licensed
`StackChan/firmware/main/hal/drivers/PY32IOExpander_Class/`. Pin mapping and audio
format follow `StackChan/firmware/main/hal/board/`. The helper changes only the
required register bits. ALDO1 supplies amplifier DVDD at 1.8 V; ALDO2 supplies
the ADC and microphones; DLDO1 supplies the backlight. AW9523 P0.2 controls
amplifier reset, and base PY32 IO1 controls motor power.
