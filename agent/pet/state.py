"""Map agent activity → a :class:`PetState`.

The one place the "what is the agent doing?" → "which row?" decision lives; CLI,
TUI and Desktop (TS mirror of this priority order) feed it the signals they track.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, NamedTuple

from agent.pet.constants import PetState


def todos_all_done(todos: Iterable[Any] | None) -> bool:
    """True iff ≥1 todo and all completed/cancelled (the ``JUMP`` celebrate beat; mirrors the TUI's ``isTodoDone``)."""
    items = list(todos or [])
    return bool(items) and all(
        (t.get("status") if isinstance(t, dict) else getattr(t, "status", None)) in ("completed", "cancelled") for t in items
    )


def derive_pet_state(
    *,
    busy: bool = False,
    awaiting_input: bool = False,
    error: bool = False,
    celebrate: bool = False,
    just_completed: bool = False,
    tool_running: bool = False,
    reasoning: bool = False,
) -> PetState:
    """Resolve the animation state from coarse activity signals.

    Priority (highest first) — only one row can show at a time, so the most
    salient signal wins:

    1. ``error``          → ``FAILED``  (a tool/turn just failed)
    2. ``celebrate``      → ``JUMP``    (explicit success beat, e.g. todos done)
    3. ``just_completed`` → ``WAVE``    (turn finished cleanly / greeting)
    4. ``awaiting_input`` → ``WAITING`` (blocked on the user — outranks the in-flight
       signals below because the turn is paused on *you*, even mid tool call)
    5. ``tool_running``   → ``RUN``
    6. ``reasoning``      → ``REVIEW``
    7. ``busy``           → ``RUN``     (turn in flight, unspecified work)
    8. otherwise          → ``IDLE``
    """
    ranked = (
        (error, PetState.FAILED),
        (celebrate, PetState.JUMP),
        (just_completed, PetState.WAVE),
        (awaiting_input, PetState.WAITING),
        (tool_running, PetState.RUN),
        (reasoning, PetState.REVIEW),
        (busy, PetState.RUN),
    )
    return next((state for flag, state in ranked if flag), PetState.IDLE)


# Rows that play once and then go quiet. ``idle`` is the resting pose: it holds
# the corner of the screen precisely when nothing is happening, so looping it
# turns into a permanent flicker in the user's periphery over a long session.
# Every other row is a live read-out of what the agent is doing and keeps
# cycling for as long as that state holds. Mirrored in the TUI's
# ``ui-tui/src/app/petAnimation.ts``.
ONE_SHOT_STATES: frozenset[str] = frozenset({PetState.IDLE})


class PetFrameStep(NamedTuple):
    """What a render loop should do on this tick."""

    index: int | None
    """Frame to paint now, or ``None`` while this row's frames are still loading."""

    cursor: int
    """Cursor to carry into the next call."""

    animating: bool
    """``False`` once the row has settled — stop advancing and stop repainting."""


def next_frame_step(state: str, cursor: int, frame_count: int) -> PetFrameStep:
    """Resolve one animation tick.

    A one-shot row walks ``0..n-1``, paints the first frame once more and settles
    there, so the pet rests on frame one rather than freezing on the last frame of
    the cycle. Re-entering the state resets the cursor, which is what buys it a
    fresh single cycle; holding the state costs nothing after it settles.
    """
    if frame_count < 1:
        return PetFrameStep(None, cursor, True)

    if state not in ONE_SHOT_STATES:
        index = cursor % frame_count
        return PetFrameStep(index, index + 1, True)

    if cursor < frame_count:
        return PetFrameStep(cursor, cursor + 1, True)

    return PetFrameStep(0, frame_count, False)
