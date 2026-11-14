#!/usr/bin/env python3
"""StackChan serial console with private per-session logs."""

import argparse
import codecs
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import select
import subprocess
import sys
import time

import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parents[2]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def file_info(path):
    if path is None:
        return None
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def git_output(*arguments):
    result = subprocess.run(
        ["git", "-C", str(ROOT), *arguments], capture_output=True, check=True
    )
    return result.stdout


def monitor(args):
    if args.duration is not None and args.duration <= 0:
        raise ValueError("duration must be greater than zero")
    firmware = file_info(args.firmware)
    weights = file_info(args.weights)
    reset = None
    if args.reset:
        from esptool.reset import HardReset

        reset = HardReset
    session = args.log_root.expanduser().resolve() / datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S.%fZ"
    )
    session.mkdir(parents=True, mode=0o700)
    metadata = {
        "session_id": session.name,
        "started_utc": utc_now(),
        "mode": "monitor",
        "reset_requested": args.reset,
        "port": args.port,
        "baud": args.baud,
        "python": sys.executable,
        "host": platform.platform(),
        "pyserial_version": importlib.metadata.version("pyserial"),
        "source_revision": git_output("rev-parse", "HEAD").decode().strip(),
        "source_dirty": bool(git_output("status", "--porcelain")),
        "tracked_diff_sha256": hashlib.sha256(git_output("diff", "HEAD")).hexdigest(),
        "firmware": firmware,
        "weights": weights,
    }
    ports = [port for port in list_ports.comports() if port.device == args.port]
    if ports:
        port = ports[0]
        metadata["usb"] = {
            "vid": port.vid,
            "pid": port.pid,
            "serial": port.serial_number,
            "description": port.description,
        }
    try:
        metadata["esptool_version"] = importlib.metadata.version("esptool")
    except importlib.metadata.PackageNotFoundError:
        pass
    metadata_path = session / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Session logs: {session}", flush=True)
    print("Type Ito commands. Ctrl-C stops the monitor.", flush=True)
    connection = serial.Serial(baudrate=args.baud, timeout=0, write_timeout=2, exclusive=True)
    connection.dtr = False
    connection.rts = False
    connection.port = args.port
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    input_decoder = codecs.getincrementaldecoder("utf-8")("replace")
    input_buffer = ""
    stdin = sys.stdin
    try:
        with (session / "serial.log").open("w", encoding="utf-8") as log:
            connection.open()
            metadata["serial_opened_utc"] = utc_now()
            if reset:
                reset(connection, uses_usb=True)()
                metadata["reset_utc"] = utc_now()
            deadline = time.monotonic() + args.duration if args.duration else None
            while deadline is None or time.monotonic() < deadline:
                readers = [connection]
                if stdin is not None:
                    readers.append(stdin)
                readable, _, _ = select.select(readers, [], [], 0.1)
                if connection in readable:
                    output = decoder.decode(connection.read(max(1, connection.in_waiting)))
                    sys.stdout.write(output)
                    sys.stdout.flush()
                    log.write(output)
                    log.flush()
                if stdin is not None and stdin in readable:
                    chunk = os.read(stdin.fileno(), 4096)
                    input_buffer += input_decoder.decode(chunk, final=not chunk)
                    commands = input_buffer.split("\n") if input_buffer else []
                    input_buffer = commands.pop() if chunk and commands else ""
                    if not chunk:
                        stdin = None
                    for command in commands:
                        command = command.rstrip("\r")
                        encoded = command.encode("utf-8")
                        if len(encoded) > 4095:
                            print("Command exceeds the firmware's 4095-byte limit.", file=sys.stderr)
                            continue
                        log.write(f"\nHOST {utc_now()} > {command}\n")
                        log.flush()
                        connection.write(encoded + b"\n")
                        connection.flush()
            metadata["exit_reason"] = "duration"
    except KeyboardInterrupt:
        metadata["exit_reason"] = "interrupt"
    except Exception as error:
        metadata["exit_reason"] = "error"
        metadata["error"] = str(error)
        raise
    finally:
        connection.close()
        metadata["ended_utc"] = utc_now()
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    console = modes.add_parser("monitor", help="Read, save and send serial console text")
    console.add_argument("--port", required=True)
    console.add_argument("--baud", type=int, default=115200)
    console.add_argument("--log-root", type=Path, default=ROOT / "esp32/logs/stackchan")
    console.add_argument("--firmware", type=Path, help="Record this flashed image's hash")
    console.add_argument("--weights", type=Path, help="Record this flashed weight file's hash")
    console.add_argument("--reset", action="store_true", help="Reset through native USB after opening the log")
    console.add_argument("--duration", type=float, help="Stop after this many seconds")
    args = parser.parse_args()
    try:
        return monitor(args)
    except (OSError, ValueError, serial.SerialException, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(main())
