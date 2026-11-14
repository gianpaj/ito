# StackChan backup preflight

Status: backup and full-flash restoration verified; factory functional boot
remains untested. Follow the
[implementation plan](../../../../plans/2026-11-14-stackchan-standalone-ito.md)
and [firmware port record](../../implemented/hardware/2026-11-14-stackchan-ito-port.md) for implementation
and build progress. The device runs an Ito validation image.

## Device and tools

- The device enumerates at `/dev/cu.usbmodem1101`, USB VID/PID `303a:1001`.
- Esptool identifies ESP32-S3 QFN56 revision v0.2 and MAC `44:1b:f6:e5:5b:58`.
- Flash ID is manufacturer `46`, device `4018`, capacity 16 MB, quad data lines.
- The saved bootloader has a DIO header and enables QIO flash at 80 MHz.
  It uses ESP-IDF v5.5.4.
- Secure boot and flash encryption are disabled. Security flags are zero.
- ESP-IDF v5.5.4 activates successfully. Its Python has esptool 4.12.dev1 and
  pyserial 3.5. Keep this environment separate from Ito's Python environment.

## Recovery access

The probe with `--before no_reset` received no response. Esptool's
`--before usb_reset` reached the ROM bootloader without physical button input.
Read commands use `--before no_reset --after no_reset` to keep the app stopped.
This prevents the app from changing flash between the two backup reads.

Use the successful USB reset before requesting physical button input. The
[manufacturer's download-mode procedure](https://docs.m5stack.com/en/StackChan)
remains the fallback. Neither method needs a flash erase.

## Backup

Private session directory:
`/Users/gianpaj_it/stackchan-backups/20261114T131625Z-441bf6e55b58/`.

`original-flash.bin` contains 16,777,216 bytes. Two full reads completed with
exit code zero and compared equal byte for byte. Each read took about 390
seconds. The redundant check copy was removed after comparison.

SHA-256:

```text
58407d7df6e736550339986d0fa5b0391a476aa82bef42c876f965c205e7364d
```

The private directory contains the backup, `SHA256SUMS`, device and tool
metadata, probe and read logs, the original partition table, firmware image
details, `README.md`, and `RESTORE.md`. Restore commands passed shell syntax
checks. The partition table, bootloader and both OTA app images passed their
embedded integrity checks. OTA metadata selects `ota_1`, StackChan 1.6.0;
`ota_0` contains StackChan 1.5.1.

The backup reads completed before the first firmware write, with the app
stopped in download mode. No eFuse write is required. Plan step 1.7 has passed
full-factory write/verify and native-image rollback/boot checks. Factory robot
app/settings functional verification remains untested.

## Remaining preparation

The Xtensa compiler, CMake and Ninja are available. Ito's existing Python
environment is `/Users/gianpaj_it/tmp/ito/.venv/`; reuse it for host work.

Model access and firmware validation are tracked in the
[firmware port record](../../implemented/hardware/2026-11-14-stackchan-ito-port.md). A separate flash format
or full erase is unnecessary; the write operation erases the sectors it replaces.
