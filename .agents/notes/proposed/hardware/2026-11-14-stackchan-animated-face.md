# Original StackChan firmware with local Ito

Status: route 2 selected; implementation is pending the user's go-ahead. The
user requests notice before implementation. This planning change does not
modify or flash firmware. Keep the working green-dot image installed.

Use the original avatar, UI and board/codec implementation, with a local Ito
backend feeding bounded PCM through the original audio output path. Preserve
one I2S owner. Mouth animation follows actual playback and drain, not text
arrival or an empty queue alone.

The supplied source declares 1.4.2, while the factory backup is 1.6.0. Official
StackChan commit `94856a77876255ceee36f2a7ffae40f572eeb1f2` declares 1.6.0 and
is the proposed baseline. The separate ignored Xiaozhi checkout also needs a
verified revision/patch record. A parent Git commit is insufficient to reproduce
that dependency.

Copying the face into standalone Ito was considered for speed. The user chose
full original-firmware integration for fidelity and maintenance. Retain that
choice; do not substitute a copied renderer to avoid integration work.

The first proposed checkpoint is an unmodified source build and memory/flash
report, without changing the device. Later work needs a PCM adapter, measured
RAM and partition budgets, cancellation/drain handling and recovery rehearsal.
The source anchors, boundaries and checkpoints are in the
[integration plan](../../../../plans/2026-11-14-stackchan-animated-face-ito.md).
