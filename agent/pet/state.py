"""Map agent activity → a :class:`PetState`.

The one place the "what is the agent doing?" → "which row?" decision lives; CLI,
TUI and Desktop (TS mirror of this priority order) feed it the signals they track.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, NamedTuple

from agent.pet.constants import MAX_FRAME_MS, MIN_FRAME_MS, PetState, loop_ms_for


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


class PetFrameStep(NamedTuple):
    """What a render loop should do on this tick."""

    index: int | None
    """Frame to paint now, or ``None`` while this row's frames are still loading."""

    cursor: int
    """Cursor to carry into the next call."""


def next_frame_step(state: str, cursor: int, frame_count: int) -> PetFrameStep:
    """Resolve one animation tick: which frame to paint, and the next cursor.

    Every row loops. What separates the resting row from the busy ones is the
    *cadence*, not the shape of the loop — see :func:`frame_interval_ms`. The
    ``None`` index is the one branch that matters here: a state whose frames are
    still loading must keep the painted frame up rather than blank the pet.
    """
    if frame_count < 1:
        return PetFrameStep(None, cursor)

    index = cursor % frame_count

    return PetFrameStep(index, index + 1)


def frame_interval_ms(state: str, frame_count: int) -> float:
    """How long one frame of *state* stays on screen.

    The loop duration is fixed per state, so the frame count decides smoothness
    rather than length — up to :data:`MAX_FRAME_MS`, which protects pets whose
    rows ship fewer real frames than the taxonomy reserves.
    """
    return min(loop_ms_for(state) / max(1, frame_count), float(MAX_FRAME_MS))


def frame_ms_sequence(state: str, frame_count: int, weights: list | None = None) -> list[float]:
    """How long each frame of *state* stays on screen, across one loop.

    Uniform unless the pet's manifest declares weights for the row. A blink is
    an event of about 150ms: held for a full beat of a breathing row it reads as
    sleep, not as life. Weights say *which frames are quick* while the loop
    duration stays owned by :data:`STATE_LOOP_MS` — so the art never has to
    restate a cadence it does not own, and a pet stays correct if that cadence
    ever changes.

    Anything malformed (wrong length, non-numbers, all zeros) falls back to
    uniform: a cosmetic manifest must never be able to freeze the pet.
    """
    count = max(0, frame_count)
    uniform = [frame_interval_ms(state, frame_count)] * count

    if not isinstance(weights, (list, tuple)) or len(weights) != count or not count:
        return uniform

    values = [float(w) for w in weights if isinstance(w, (int, float)) and not isinstance(w, bool) and w > 0]
    if len(values) != count:
        return uniform

    loop_ms = frame_interval_ms(state, frame_count) * count
    total = sum(values)

    return [min(max(loop_ms * w / total, float(MIN_FRAME_MS)), float(MAX_FRAME_MS)) for w in values]


def ticks_for(state: str, frame_count: int, tick_seconds: float, *, frame_ms: float | None = None) -> int:
    """Frame interval expressed in whole ticks of a *tick_seconds* render loop.

    The CLI pane animates from a fixed 160ms thread, and rounding to whole ticks
    is what keeps the fast rows exactly as they have always been (one frame per
    tick) instead of quantising 183ms up to 320ms and halving their speed.
    """
    if tick_seconds <= 0:
        return 1

    # Piso, não arredondamento: arredondar faria uma linha cuja cadência fica
    # entre um tique e meio e dois (a `wave`, 275ms) passar a segurar dois
    # tiques e ficar 16% mais lenta sem ninguém ter pedido. Com piso, só quem
    # tem cadência própria de verdade (o `idle`) muda de ritmo.
    interval = frame_interval_ms(state, frame_count) if frame_ms is None else frame_ms

    return max(1, int(interval / 1000.0 / tick_seconds))
