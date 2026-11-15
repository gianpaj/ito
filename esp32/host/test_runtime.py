#!/usr/bin/env python3
"""Run production C playback, lifecycle and worker checkpoints with host mocks."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

HOST = Path(__file__).resolve().parent
MAIN = HOST.parent / "firmware/main/main.c"
FUNCTIONS = (
    "service_stopping", "service_checkpoint", "audio_mute", "cancel_flush", "audio_write", "play_task", "cancel_job",
    "fe_busy", "fe_release", "fe_submit",
)

LIFECYCLE_FUNCTIONS = (
    "allocate_weight_copy", "request_stop", "cancel_job", "itofs_service_reserve_hot", "workers_parked", "wait_parked",
    "reset_playback_queues", "release_inference", "itofs_service_stop",
    "itofs_service_resume", "itofs_service_borrow_hot", "itofs_service_return_hot",
    "itofs_service_start",
)


def function(source, name):
    matches = list(re.finditer(
        rf"^(?:static )?(?:esp_err_t|int|void) {name}\([^\n]*\)\s*\{{",
        source, re.MULTILINE,
    ))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one preprocessed definition of {name}")
    match = matches[0]
    opening = source.index("{", match.start())
    depth = 0
    # Ignore braces in C string and character literals.
    tokens = re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', source[opening:])
    for token in tokens:
        value = token.group()
        depth += (value == "{") - (value == "}")
        if depth == 0:
            return source[match.start():opening + token.end()]
    raise RuntimeError(f"Unbalanced definition of {name}")


def main():
    compiler = shlex.split(os.environ.get("CC", "cc"))
    # The compiler selects the embedded branches and expands firmware constants.
    # Includes are supplied by the fixture instead of ESP-IDF. Function bodies
    # come directly from main.c, so the fixtures do not copy runtime logic.
    source = re.sub(r"^\s*#\s*include[^\n]*", "", MAIN.read_text(), flags=re.MULTILINE)
    selected = subprocess.run(
        compiler + ["-E", "-P", "-x", "c", "-DITOFS_EMBEDDED=1",
                    "-DCONFIG_ITOFS_FRONTEND=1", "-"],
        input=source, text=True, capture_output=True, check=True,
    ).stdout
    with tempfile.TemporaryDirectory(prefix="ito-runtime-test-") as directory:
        temporary = Path(directory)
        for fixture, functions in (("host_test_runtime.c", FUNCTIONS),
                                   ("host_test_lifecycle.c", LIFECYCLE_FUNCTIONS),
                                   ("host_test_checkpoint.c", ("service_stopping", "request_stop", "workers_parked", "service_checkpoint"))):
            (temporary / "production_functions.inc").write_text(
                "\n\n".join(function(selected, name) for name in functions)
            )
            executable = temporary / fixture.removesuffix(".c")
            subprocess.run(
                compiler + ["-std=c11", "-pthread", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-function", "-I", str(temporary),
                            "-I", str(HOST / "runtime_mock"),
                            "-I", str(HOST.parent / "runtime"),
                            str(HOST / fixture), "-o", str(executable)],
                check=True,
            )
            subprocess.run([str(executable)], check=True, timeout=15)


if __name__ == "__main__":
    main()
