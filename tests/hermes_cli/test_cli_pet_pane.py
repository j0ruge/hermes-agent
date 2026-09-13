"""The base-CLI petdex pane: reactive half-block sprite above the prompt.

Mirrors the TUI's PetPane. The methods are tested in isolation via __new__ so
we don't pay the full HermesCLI.__init__ cost; a synthetic spritesheet exercises
the real engine decode + half-block fragment building.
"""

from __future__ import annotations

import threading

import pytest

from agent.pet import store
from agent.pet.constants import FRAME_H, FRAME_W
from agent.pet.render import PetRenderer
from cli import HermesCLI


@pytest.fixture
def boba_like(tmp_path, monkeypatch):
    """Install a synthetic pet into a temp HERMES_HOME and return its slug."""
    from PIL import Image

    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))

    cols, rows = 8, 9
    sheet = Image.new("RGBA", (FRAME_W * cols, FRAME_H * rows), (0, 0, 0, 0))
    for r in range(rows):
        color = (20 + r * 25, 60, 120, 255)
        for c in range(cols):
            block = Image.new("RGBA", (FRAME_W, FRAME_H), (color[0], color[1] + c * 20, color[2], 255))
            sheet.paste(block, (c * FRAME_W, r * FRAME_H))

    pet_dir = store.pets_dir() / "boba"
    pet_dir.mkdir(parents=True, exist_ok=True)
    sheet.save(pet_dir / "spritesheet.webp")
    (pet_dir / "pet.json").write_text(
        '{"id":"boba","displayName":"Boba","description":"d","spritesheetPath":"spritesheet.webp"}'
    )
    return "boba"


def _make_cli():
    cli_obj = HermesCLI.__new__(HermesCLI)
    cli_obj._app = None
    cli_obj._pet_lock = threading.Lock()
    cli_obj._pet_enabled = False
    cli_obj._pet_renderer = None
    cli_obj._pet_slug = ""
    cli_obj._pet_cols = 18
    cli_obj._pet_scale = 0.7
    cli_obj._pet_frames_cache = {}
    cli_obj._pet_kitty_cache = {}
    cli_obj._pet_kitty_image_id = 0
    cli_obj._pet_kitty_pending = ""
    cli_obj._pet_frame_idx = 0
    cli_obj._pet_paint_idx = 0
    cli_obj._pet_anim_state = ""
    cli_obj._agent_running = False
    # Transient-beat + reasoning state (set by HermesCLI.__init__ in production).
    cli_obj._pet_event = ""
    cli_obj._pet_event_until = 0.0
    cli_obj._pet_reasoning = False
    # Blocking-modal state — a live one maps the pet to `waiting`.
    cli_obj._approval_state = None
    cli_obj._clarify_state = None
    cli_obj._sudo_state = None
    cli_obj._secret_state = None
    cli_obj._slash_confirm_state = None
    return cli_obj


def test_pet_state_tracks_agent_running():
    cli_obj = _make_cli()
    assert cli_obj._derive_pet_state() == "idle"
    cli_obj._agent_running = True
    assert cli_obj._derive_pet_state() == "run"


def test_pet_state_waits_on_a_blocking_modal():
    # A live clarify/approval pauses the agent on the user → `waiting`, even
    # while the turn is technically still running.
    cli_obj = _make_cli()
    cli_obj._agent_running = True
    cli_obj._clarify_state = {"question": "?"}
    assert cli_obj._derive_pet_state() == "waiting"


def test_pet_pane_collapsed_when_disabled():
    # No renderer resolved → the window reports zero height and no fragments,
    # so it's invisible for users without a pet.
    cli_obj = _make_cli()
    assert cli_obj._pet_widget_height() == 0
    assert cli_obj._pet_fragments() == []


def test_pet_fragments_render_half_blocks(boba_like):
    cli_obj = _make_cli()
    cli_obj._pet_renderer = PetRenderer(
        str(store.load_pet("boba").spritesheet), mode="unicode", scale=0.4, unicode_cols=14
    )
    cli_obj._pet_cols = 14
    cli_obj._pet_enabled = True

    height = cli_obj._pet_widget_height()
    assert height > 0

    frags = cli_obj._pet_fragments()
    assert frags, "expected fragments for an enabled pet"
    # Each fragment is a (style, text) pair; glyphs are half-blocks or blanks.
    glyphs = {text for _, text in frags}
    assert glyphs <= {"▀", "▄", " ", "\n"}
    # Opaque cells carry a truecolor foreground style.
    assert any(text == "▀" and "fg:#" in style for style, text in frags)
    # Row count in the fragment stream matches the reported window height.
    assert sum(1 for _, text in frags if text == "\n") == height - 1


def test_pet_resolve_config_enables_and_disables(boba_like):
    from hermes_cli.config import load_config, save_config

    cli_obj = _make_cli()

    cfg = load_config()
    cfg.setdefault("display", {}).setdefault("pet", {})
    cfg["display"]["pet"].update({"enabled": True, "slug": "boba"})
    save_config(cfg)

    cli_obj._pet_resolve_config()
    assert cli_obj._pet_enabled is True
    assert cli_obj._pet_renderer is not None
    assert cli_obj._pet_slug == "boba"

    cfg["display"]["pet"]["enabled"] = False
    save_config(cfg)
    cli_obj._pet_resolve_config()
    assert cli_obj._pet_enabled is False
    assert cli_obj._pet_renderer is None


def test_pet_fragments_render_kitty_placeholders(boba_like):
    from agent.pet import render

    cli_obj = _make_cli()
    pet = store.load_pet("boba")
    assert pet is not None
    cli_obj._pet_renderer = PetRenderer(str(pet.spritesheet), mode="kitty", scale=0.4)
    cli_obj._pet_slug = "boba"
    cli_obj._pet_kitty_image_id = render.kitty_image_id("boba")
    cli_obj._pet_enabled = True

    frags = cli_obj._pet_fragments()
    assert frags
    assert any("\U0010eeee" in text for _, text in frags)
    payload = cli_obj._pet_kitty_payload_for("idle")
    assert payload is not None
    color = render.kitty_color_hex(payload["image_id"])
    assert all(f"fg:{color}" in style for style, text in frags if text != "\n")
    assert cli_obj._pet_widget_height() > 0

    cli_obj._pet_queue_kitty_frame("idle")
    assert cli_obj._pet_kitty_pending.startswith("\x1b_G")

    class Output:
        def __init__(self):
            self.raw = ""
            self.flushed = False

        def write_raw(self, text):
            self.raw += text

        def flush(self):
            self.flushed = True

    class App:
        output = Output()

    app = App()
    cli_obj._pet_flush_kitty_frame(app)
    assert app.output.raw.startswith("\x1b_G")
    assert app.output.flushed is True
    assert cli_obj._pet_kitty_pending == ""


def test_pet_off_clears_pending_kitty_frame(boba_like):
    from hermes_cli.config import load_config, save_config

    cli_obj = _make_cli()
    cli_obj._pet_kitty_pending = "stale-apc"
    cfg = load_config()
    cfg.setdefault("display", {}).setdefault("pet", {}).update(
        {"enabled": True, "slug": "boba", "render_mode": "off"}
    )
    save_config(cfg)

    cli_obj._pet_resolve_config()

    assert cli_obj._pet_enabled is False
    assert cli_obj._pet_renderer is None
    assert cli_obj._pet_kitty_pending == ""


def test_pet_resolve_wezterm_stays_unicode(boba_like, monkeypatch):
    from hermes_cli.config import load_config, save_config

    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("TERM_PROGRAM", "WezTerm")
    cli_obj = _make_cli()
    cfg = load_config()
    cfg.setdefault("display", {}).setdefault("pet", {}).update(
        {"enabled": True, "slug": "boba", "render_mode": "auto"}
    )
    save_config(cfg)

    cli_obj._pet_resolve_config()

    assert cli_obj._pet_renderer is not None
    assert cli_obj._pet_renderer.mode == "unicode"


def test_pet_resolve_ghostty_uses_kitty(boba_like, monkeypatch):
    from hermes_cli.config import load_config, save_config

    monkeypatch.delenv("WEZTERM_PANE", raising=False)
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.setenv("TERM", "xterm-ghostty")
    monkeypatch.setenv("TERM_PROGRAM", "ghostty")
    cli_obj = _make_cli()
    cfg = load_config()
    cfg.setdefault("display", {}).setdefault("pet", {}).update(
        {"enabled": True, "slug": "boba", "render_mode": "auto"}
    )
    save_config(cfg)

    cli_obj._pet_resolve_config()

    assert cli_obj._pet_renderer is not None
    assert cli_obj._pet_renderer.mode == "kitty"


def test_force_full_redraw_requeues_kitty_frame(boba_like, monkeypatch):
    from agent.pet import render

    cli_obj = _make_cli()
    pet = store.load_pet("boba")
    assert pet is not None
    cli_obj._pet_renderer = PetRenderer(str(pet.spritesheet), mode="kitty", scale=0.4)
    cli_obj._pet_enabled = True
    cli_obj._pet_kitty_image_id = render.kitty_image_id("boba")
    cli_obj._terminal_io_broken = False
    cli_obj._clear_prompt_toolkit_screen = lambda *a, **k: None
    cli_obj._redraw_rebuilds_scrollback = lambda: False

    class App:
        def invalidate(self):
            self.invalidated = True

    cli_obj._app = App()
    monkeypatch.setattr("cli._replay_output_history", lambda: None)

    cli_obj._force_full_redraw()

    assert cli_obj._pet_kitty_pending.startswith("\x1b_G")


# ── animation loop ────────────────────────────────────────────────────────
#
# `idle` holds the pane while nothing happens, so looping it forever is a
# permanent flicker in the corner of the screen. These drive one tick at a time
# (the loop body without its `time.sleep`) and read back the frame that actually
# reached the terminal.


def _kitty_cli(slug="boba"):
    from agent.pet import render

    cli_obj = _make_cli()
    pet = store.load_pet(slug)
    assert pet is not None
    cli_obj._pet_renderer = PetRenderer(str(pet.spritesheet), mode="kitty", scale=0.4)
    cli_obj._pet_slug = slug
    cli_obj._pet_kitty_image_id = render.kitty_image_id(slug)
    cli_obj._pet_enabled = True
    return cli_obj


def _transmitted(cli_obj, state, ticks):
    """Frame indices actually transmitted over `ticks` ticks, oldest first."""
    frames = cli_obj._pet_kitty_payload_for(state)["frames"]
    painted = []
    for _ in range(ticks):
        if cli_obj._pet_anim_tick():
            painted.append(frames.index(cli_obj._pet_kitty_pending))
    return painted


def test_idle_plays_one_cycle_then_rests_on_the_first_frame(boba_like):
    cli_obj = _kitty_cli()
    count = len(cli_obj._pet_kitty_payload_for("idle")["frames"])

    assert _transmitted(cli_obj, "idle", count + 1) == list(range(count)) + [0]


def test_idle_never_restarts_however_long_the_agent_sits_still(boba_like):
    cli_obj = _kitty_cli()
    count = len(cli_obj._pet_kitty_payload_for("idle")["frames"])

    painted = _transmitted(cli_obj, "idle", count * 20)

    assert painted == list(range(count)) + [0]


def test_a_settled_pet_asks_for_no_repaints(boba_like):
    cli_obj = _kitty_cli()
    count = len(cli_obj._pet_kitty_payload_for("idle")["frames"])
    for _ in range(count + 1):
        cli_obj._pet_anim_tick()

    assert [cli_obj._pet_anim_tick() for _ in range(5)] == [False] * 5


def test_an_active_row_keeps_looping(boba_like):
    cli_obj = _kitty_cli()
    cli_obj._agent_running = True
    count = len(cli_obj._pet_kitty_payload_for("run")["frames"])

    painted = _transmitted(cli_obj, "run", count * 2)

    assert painted == list(range(count)) * 2


def test_falling_back_to_idle_buys_exactly_one_fresh_cycle(boba_like):
    cli_obj = _kitty_cli()
    count = len(cli_obj._pet_kitty_payload_for("idle")["frames"])
    _transmitted(cli_obj, "idle", count * 3)

    cli_obj._agent_running = True
    _transmitted(cli_obj, "run", 3)
    cli_obj._agent_running = False

    assert _transmitted(cli_obj, "idle", count * 3) == list(range(count)) + [0]


def test_half_block_path_also_rests_on_the_first_frame(boba_like):
    cli_obj = _make_cli()
    cli_obj._pet_renderer = PetRenderer(
        str(store.load_pet("boba").spritesheet), mode="unicode", scale=0.4, unicode_cols=14
    )
    cli_obj._pet_cols = 14
    cli_obj._pet_enabled = True

    def styles():
        return tuple(style for style, text in cli_obj._pet_fragments() if text != "\n")

    seen = []
    for _ in range(40):
        if cli_obj._pet_anim_tick():
            seen.append(styles())

    assert len(seen) > 2, "expected the idle row to animate at least once"
    assert seen[-1] == seen[0], "settled on a frame other than the first"
