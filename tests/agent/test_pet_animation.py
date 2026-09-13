"""The animation policy: which frame to paint, and whether to keep ticking.

`idle` is the resting row — it holds the corner of the screen while nothing
happens, so looping it forever is a permanent flicker. It plays one cycle and
settles on the first frame; the live-readout rows keep cycling.
"""

from __future__ import annotations

import pytest

from agent.pet.constants import PetState
from agent.pet.state import next_frame_step


def _play(state, count, ticks=24):
    """Walk the policy the way a render loop does: paint, carry the cursor, stop."""
    painted, cursor, settled = [], 0, False
    for _ in range(ticks):
        step = next_frame_step(state, cursor, count)
        painted.append(step.index)
        cursor = step.cursor
        if not step.animating:
            settled = True
            break
    return painted, cursor, settled


def test_no_frames_yet_paints_nothing_and_keeps_ticking():
    step = next_frame_step(PetState.IDLE, 3, 0)
    assert (step.index, step.cursor, step.animating) == (None, 3, True)


def test_idle_plays_one_cycle_then_rests_on_the_first_frame():
    painted, cursor, settled = _play(PetState.IDLE, 6)
    assert painted == [0, 1, 2, 3, 4, 5, 0]
    assert (cursor, settled) == (6, True)


def test_idle_stays_on_the_first_frame_for_any_later_cursor():
    for cursor in (6, 7, 99):
        step = next_frame_step(PetState.IDLE, cursor, 6)
        assert (step.index, step.cursor, step.animating) == (0, 6, False)


@pytest.mark.parametrize("count", [1, 2, 5, 9])
def test_idle_settles_whatever_the_frame_count(count):
    painted, _, settled = _play(PetState.IDLE, count)
    assert settled is True
    assert painted[-1] == 0
    assert len(painted) == count + 1


@pytest.mark.parametrize(
    "state",
    [PetState.RUN, PetState.REVIEW, PetState.WAITING, PetState.WAVE, PetState.JUMP, PetState.FAILED],
)
def test_active_rows_keep_looping(state):
    painted, _, settled = _play(state, 3, ticks=7)
    assert settled is False
    assert painted == [0, 1, 2, 0, 1, 2, 0]
