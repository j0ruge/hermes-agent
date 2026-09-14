"""A linha de animação: qual quadro pintar, e em que ritmo.

`idle` é a linha de repouso — fica na tela justamente quando nada acontece. Ela
cicla como as outras, mas numa cadência de respiração (~4,4s a volta) em vez do
~1s dos estados que são leitura ao vivo do que o agente faz.
"""

from __future__ import annotations

import pytest

from agent.pet.constants import LOOP_MS, MAX_FRAME_MS, MIN_FRAME_MS, PetState, loop_ms_for
from agent.pet.state import frame_interval_ms, frame_ms_sequence, next_frame_step, ticks_for

CLI_TICK_S = 0.16


def _play(state, count, ticks=14):
    """Anda a política como um render loop faz: pinta, carrega o cursor."""
    painted, cursor = [], 0
    for _ in range(ticks):
        step = next_frame_step(state, cursor, count)
        painted.append(step.index)
        cursor = step.cursor
    return painted


def test_no_frames_yet_paints_nothing_and_keeps_the_painted_frame():
    step = next_frame_step(PetState.IDLE, 3, 0)
    assert (step.index, step.cursor) == (None, 3)


@pytest.mark.parametrize("state", list(PetState))
def test_every_row_loops(state):
    assert _play(state, 3, ticks=7) == [0, 1, 2, 0, 1, 2, 0]


@pytest.mark.parametrize("count", [1, 2, 6, 8])
def test_the_loop_closes_whatever_the_frame_count(count):
    painted = _play(PetState.IDLE, count, ticks=count * 2)
    assert painted == list(range(count)) * 2


def test_idle_breathes_slower_than_the_live_readout_rows():
    assert loop_ms_for("idle") == 4800
    assert loop_ms_for("run") == LOOP_MS
    assert loop_ms_for("review") == LOOP_MS


def test_an_unknown_state_falls_back_to_the_baseline_loop():
    assert loop_ms_for("nao-existe") == LOOP_MS


def test_the_enum_and_its_string_agree():
    assert loop_ms_for(PetState.IDLE) == loop_ms_for("idle")


def test_frame_interval_splits_the_loop_across_the_real_frames():
    assert frame_interval_ms("idle", 6) == 800
    assert frame_interval_ms("run", 6) == pytest.approx(183.33, abs=0.01)


def test_a_ragged_row_is_clamped_instead_of_holding_one_frame_for_seconds():
    # Um pet cujo idle só tenha 2 quadros reais daria 2200ms por quadro: isso não
    # é respiração, é slideshow. O teto protege o pet dos outros.
    assert frame_interval_ms("idle", 2) == MAX_FRAME_MS


def test_frame_interval_survives_an_empty_row():
    assert frame_interval_ms("idle", 0) > 0


def test_the_cli_quantises_the_cadence_into_whole_ticks():
    # O painel do CLI acorda a cada 160ms. Arredondar para tiques inteiros é o
    # que mantém os estados rápidos exatamente como sempre foram (1 tique por
    # quadro) em vez de dobrar a volta deles para 320ms.
    assert ticks_for("run", 6, CLI_TICK_S) == 1
    assert ticks_for("idle", 6, CLI_TICK_S) == 5
    # `wave` pede 275ms, entre um tique e meio e dois. Arredondar a poria em 2
    # tiques e a deixaria 16% mais lenta; o piso preserva o ritmo de sempre.
    assert ticks_for("wave", 4, CLI_TICK_S) == 1


def test_a_tick_count_is_never_zero():
    assert ticks_for("run", 60, CLI_TICK_S) == 1


# ── duração por quadro ────────────────────────────────────────────────────
#
# Uma piscada é um evento de ~150ms. Segurá-la por um quadro inteiro de
# respiração (800ms) lê como sono, não como vida. Os pesos deixam a arte dizer
# quais quadros são rápidos sem tirar de `STATE_LOOP_MS` a posse da duração da
# volta: cada quadro recebe uma fatia proporcional ao seu peso.


def test_a_row_without_weights_is_uniform():
    assert frame_ms_sequence("idle", 6) == [800.0] * 6


def test_weights_shorten_one_frame_and_keep_the_loop_length():
    seq = frame_ms_sequence("idle", 6, [1, 1, 1, 1, 0.2, 1])

    assert sum(seq) == pytest.approx(loop_ms_for("idle"))
    assert seq[4] < 250
    assert all(q > 700 for i, q in enumerate(seq) if i != 4)


def test_weights_of_the_wrong_length_are_ignored():
    assert frame_ms_sequence("idle", 6, [1, 1]) == [800.0] * 6


def test_a_frame_is_never_shorter_than_the_eye_can_see():
    seq = frame_ms_sequence("idle", 6, [1, 1, 1, 1, 0.001, 1])

    assert seq[4] >= MIN_FRAME_MS


def test_garbage_weights_fall_back_to_uniform():
    assert frame_ms_sequence("idle", 6, ["a", None, 1, 1, 1, 1]) == [800.0] * 6
    assert frame_ms_sequence("idle", 6, [0, 0, 0, 0, 0, 0]) == [800.0] * 6


def test_the_cli_quantises_a_quick_frame_to_a_single_tick():
    seq = frame_ms_sequence("idle", 6, [1, 1, 1, 1, 0.2, 1])

    assert ticks_for("idle", 6, CLI_TICK_S, frame_ms=seq[4]) == 1
    assert ticks_for("idle", 6, CLI_TICK_S, frame_ms=seq[0]) == 5
