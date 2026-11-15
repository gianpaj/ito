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
import re
import select
import subprocess
import sys
import time
import wave

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
    print("Type Ito/conversation commands. Ctrl-C stops the monitor.", flush=True)
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


def load_pcm16_wav(path):
    """Accept uncompressed mono PCM16 at 16 kHz, from one sample to ten seconds."""
    try:
        with wave.open(str(path), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) != (1, 2, 16000, "NONE"):
                raise ValueError("WAV must be uncompressed mono PCM16 at 16000 Hz")
            samples = audio.getnframes()
            if not 1 <= samples <= 160000:
                raise ValueError("WAV must contain 1..160000 samples, at most 10 seconds")
            pcm = audio.readframes(samples)
            if len(pcm) != samples * 2:
                raise ValueError("WAV data is truncated")
            return pcm
    except (wave.Error, EOFError) as error:
        raise ValueError(f"Invalid PCM WAV: {error}") from error


class TranscriptionSerial:
    """Bounded line protocol; logs contain private audio and transcript data."""

    def __init__(self, connection, log, commands):
        self.connection, self.log, self.commands = connection, log, commands
        self.buffer = b""
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")

    def send(self, command):
        data = command.encode("ascii") + b"\n"
        self.commands.write(f"HOST {utc_now()} > {command}\n")
        self.commands.flush()
        if self.connection.write(data) != len(data):
            raise OSError("Incomplete USB command write")

    def line(self, deadline):
        while time.monotonic() < deadline:
            if b"\n" in self.buffer:
                raw, self.buffer = self.buffer.split(b"\n", 1)
                line = raw.decode("utf-8", "replace").rstrip("\r")
                if line.startswith("ERROR"):
                    raise RuntimeError(line)
                return line
            data = self.connection.read(max(1, self.connection.in_waiting))
            if data:
                self.log.write(self.decoder.decode(data))
                self.log.flush()
                self.buffer += data
                if len(self.buffer) > 65536:
                    raise RuntimeError("Device emitted an overlong serial line")
        raise TimeoutError("Timed out waiting for the device")

    def wait(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while True:
            line = self.line(deadline)
            if predicate(line):
                return line

    def ready(self, timeout=90):
        deadline = time.monotonic() + timeout
        probe = 0.0
        idle = False
        while time.monotonic() < deadline:
            if time.monotonic() >= probe:
                self.send("status")
                probe = time.monotonic() + 2
            try:
                line = self.line(min(deadline, probe))
            except TimeoutError:
                continue
            if re.fullmatch(r"CONVERSATION turn=\d+ state=idle", line):
                idle = True
            elif idle and (line == "READY" or line.startswith("READY ")):
                return
        raise TimeoutError("Conversation firmware did not become ready within 90 seconds")

    def transcribe(self, pcm, echo=False):
        samples = len(pcm) // 2
        self.send(f"pcm begin {samples}")
        begin = self.wait(lambda line: line.startswith("OK pcm begin "), 2)
        match = re.fullmatch(r"OK pcm begin turn=(\d+) samples=(\d+)", begin)
        if not match or int(match[2]) != samples:
            raise RuntimeError(f"Unexpected upload acknowledgement: {begin}")
        turn = int(match[1])
        for start in range(0, len(pcm), 512):
            chunk = pcm[start:start + 512]
            self.send("pcm data " + chunk.hex())
            acknowledgement = self.wait(lambda line: line.startswith("OK pcm data "), 2)
            expected = f"OK pcm data samples={(start + len(chunk)) // 2}"
            if acknowledgement != expected:
                raise RuntimeError(f"Expected {expected!r}, received {acknowledgement!r}")
        self.send("send")
        self.wait(lambda line: line == "OK send", 2)
        deadline = time.monotonic() + 120
        transcript = None
        while True:
            line = self.line(deadline)
            match = re.fullmatch(r"TRANSCRIPT turn=(\d+): (.*)", line)
            if match:
                if int(match[1]) != turn:
                    raise RuntimeError("Transcript belongs to another turn")
                transcript = match[2]
            if line.startswith("CONVERSATION READY"):
                if transcript is None:
                    raise RuntimeError("Recognition finished without a transcript")
                break
        if echo:
            self.send("echo")
            self.wait(lambda line: line.startswith("OK text queued"), 2)
            self.wait(lambda line: line == "READY" or line.startswith("READY "), 120)
        return {"turn": turn, "samples": samples, "sample_rate_hz": 16000,
                "transcript": transcript, "echo_requested": echo}


def transcribe(args):
    pcm = load_pcm16_wav(args.wav.expanduser())
    metadata = {"mode": "transcribe", "started_utc": utc_now(), "port": args.port,
                "baud": args.baud, "audio": file_info(args.wav),
                "firmware": file_info(args.firmware), "weights": file_info(args.weights),
                "asr_weights": file_info(args.asr_weights), "echo_requested": args.echo,
                "source_revision": git_output("rev-parse", "HEAD").decode().strip(),
                "source_dirty": bool(git_output("status", "--porcelain"))}
    session = args.log_root.expanduser().resolve() / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    session.mkdir(parents=True, mode=0o700)
    metadata_path = session / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Private session logs: {session}", flush=True)
    connection = serial.Serial(baudrate=args.baud, timeout=0.1, write_timeout=2, exclusive=True)
    connection.dtr = connection.rts = False
    connection.port = args.port
    channel = None
    try:
        with (session / "serial.log").open("w", encoding="utf-8") as log, (session / "commands.log").open("w", encoding="utf-8") as commands:
            connection.open()
            channel = TranscriptionSerial(connection, log, commands)
            channel.ready()
            result = channel.transcribe(pcm, args.echo)
            (session / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(f"TRANSCRIPT turn={result['turn']}: {result['transcript']}", flush=True)
            metadata["exit_reason"] = "complete"
    except BaseException as error:
        metadata["exit_reason"] = "interrupt" if isinstance(error, KeyboardInterrupt) else "error"
        metadata["error"] = str(error)
        if channel is not None:
            try:
                channel.send("cancel")
            except (OSError, serial.SerialException):
                pass
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
    transcription = modes.add_parser("transcribe", help="Upload a <=10-second WAV and recognize it locally")
    transcription.add_argument("wav", type=Path)
    transcription.add_argument("--port", required=True)
    transcription.add_argument("--baud", type=int, default=115200)
    transcription.add_argument("--log-root", type=Path, default=ROOT / "esp32/logs/stackchan")
    transcription.add_argument("--firmware", type=Path)
    transcription.add_argument("--weights", type=Path, help="Record the Ito model hash")
    transcription.add_argument("--asr-weights", type=Path, help="Record the Oido model hash")
    transcription.add_argument("--echo", action="store_true", help="Speak the transcript with Ito after recognition")
    args = parser.parse_args()
    try:
        return monitor(args) if args.mode == "monitor" else transcribe(args)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, serial.SerialException, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(main())
