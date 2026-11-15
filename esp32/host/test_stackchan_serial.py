#!/usr/bin/env python3
"""WAV validation and the production USB transcription protocol, without hardware."""
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

spec = importlib.util.spec_from_file_location("stackchan", Path(__file__).resolve().parents[1] / "tools/stackchan.py")
console = importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)


class FakeSerial:
    def __init__(self, bad_ack=False, error=False, wrong_turn=False, fragment=17):
        self.received = bytearray()
        self.pending = bytearray()
        self.commands = []
        self.bad_ack, self.error, self.wrong_turn, self.fragment = bad_ack, error, wrong_turn, fragment

    @property
    def in_waiting(self):
        return len(self.pending)

    def write(self, data):
        command = data.decode().strip()
        self.commands.append(command)
        if command == "status":
            response = "CONVERSATION turn=0 state=idle\nREADY\n"
        elif command.startswith("pcm begin "):
            response = f"OK pcm begin turn=7 samples={command.split()[-1]}\n"
        elif command.startswith("pcm data "):
            chunk = bytes.fromhex(command[9:])
            assert len(chunk) <= 512
            self.received.extend(chunk)
            count = len(self.received) // 2 + self.bad_ack
            response = f"OK pcm data samples={count}\n"
        elif command == "send":
            response = "OK send\n"
            if self.error:
                response += "ERROR recognition turn=7: ESP_FAIL\n"
            else:
                response += f"TRANSCRIPT turn={8 if self.wrong_turn else 7}: hello café\nCONVERSATION READY: echo repeats the transcript\n"
        elif command == "echo":
            response = "OK text queued (11 bytes)\nREADY\n"
        else:
            raise AssertionError(command)
        self.pending.extend(response.encode())
        return len(data)

    def read(self, size):
        data = self.pending[:min(size, self.fragment)]
        del self.pending[:len(data)]
        return bytes(data)


class SerialTests(unittest.TestCase):
    def channel(self, **kwargs):
        port = FakeSerial(**kwargs)
        channel = console.TranscriptionSerial(port, io.StringIO(), io.StringIO())
        return port, channel

    def test_exact_chunks_reassembly_turn_and_echo(self):
        port, channel = self.channel(fragment=1)
        channel.ready()
        pcm = bytes(range(256)) * 5 + b"\x01\x00"
        result = channel.transcribe(pcm, echo=True)
        self.assertEqual(bytes(port.received), pcm)
        self.assertEqual(result["transcript"], "hello café")
        self.assertEqual(result["turn"], 7)
        self.assertEqual(port.commands[-2:], ["send", "echo"])
        self.assertEqual(sum(c.startswith("pcm data ") for c in port.commands), 3)
        self.assertIn("hello café", channel.log.getvalue())

    def test_ready_drains_queued_boot_status_before_upload(self):
        class BootTail(FakeSerial):
            def write(self, data):
                count = super().write(data)
                if data == b"status\n":
                    self.pending.extend(b"STATUS pending report\nREADY\n")
                return count
        port = BootTail(fragment=1)
        channel = console.TranscriptionSerial(port, io.StringIO(), io.StringIO())
        channel.ready()
        self.assertFalse(channel.buffer or port.pending)
        self.assertEqual(channel.transcribe(b"\x00\x00")["turn"], 7)

    def test_bad_ack_stops_before_send(self):
        port, channel = self.channel(bad_ack=True)
        with self.assertRaisesRegex(RuntimeError, "Expected"):
            channel.transcribe(b"\x00\x00")
        self.assertNotIn("send", port.commands)

    def test_recognition_error_and_wrong_turn(self):
        for options in ({"error": True}, {"wrong_turn": True}):
            _, channel = self.channel(**options)
            with self.assertRaises(RuntimeError):
                channel.transcribe(b"\x00\x00")

    def test_deadline(self):
        _, channel = self.channel()
        with patch.object(console.time, "monotonic", side_effect=[1, 4]):
            with self.assertRaises(TimeoutError):
                channel.wait(lambda line: True, 2)

    def test_wav_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.wav"
            for channels, width, rate, samples, valid in (
                (1, 2, 16000, 1, True), (1, 2, 16000, 160000, True),
                (1, 2, 16000, 160001, False), (1, 2, 16000, 0, False),
                (2, 2, 16000, 20, False), (1, 1, 16000, 20, False), (1, 2, 24000, 20, False),
            ):
                with wave.open(str(path), "wb") as audio:
                    audio.setparams((channels, width, rate, 0, "NONE", "not compressed"))
                    audio.writeframes(b"\x00" * channels * width * samples)
                if valid:
                    self.assertEqual(len(console.load_pcm16_wav(path)), samples * 2)
                else:
                    with self.assertRaises(ValueError):
                        console.load_pcm16_wav(path)
            path.write_bytes(b"not a wav")
            with self.assertRaises(ValueError):
                console.load_pcm16_wav(path)
            with wave.open(str(path), "wb") as audio:
                audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                audio.writeframes(b"\x00" * 100)
            path.write_bytes(path.read_bytes()[:-10])
            with self.assertRaisesRegex(ValueError, "truncated"):
                console.load_pcm16_wav(path)


if __name__ == "__main__":
    unittest.main()
