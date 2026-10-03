"""mods/axiom.illustrations/main.py

Official mod: axiom.illustrations (AI Scene & Character Illustration Generator)
Provides:
1. Contextual scene image generation via local Stable Diffusion WebUI or ComfyUI.
2. Hook 'axiom.step:after_step' generating scene visuals asynchronously post-commit.
3. Custom storage policy 'assets' ensuring surgical rollback of generated PNG files during rewind.
4. Public service 'illustrations' exposing generate_turn_image and truncate_assets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from axiom import config as axiom_config
from axiom.config import AppConfig
from axiom.kernel.context import ModContext
from axiom.logger import logger
from axiom.savestore import truncate_assets_in


class IllustrationsService:
    """Public service exposed by axiom.illustrations."""

    def __init__(self, data_root: Path | None = None) -> None:
        self.data_root = data_root
        # Data root of each save seen in a turn (a Session may inject its own
        # data_dir): rewind and fork then touch the right assets folder.
        self._save_roots: dict[str, Path] = {}

    def remember_root(self, save_id: str, root: Path | None) -> None:
        if save_id and root is not None:
            self._save_roots[save_id] = Path(root)

    def _root_for(self, save_id: str, data_root: Path | None = None) -> Path:
        # Explicit root, else the root seen in this save's turns, else the data root
        # in effect (a Session with its own data_dir scopes it during rewind/fork).
        from axiom import paths
        return Path(data_root or self._save_roots.get(save_id) or self.data_root or paths._data_root())

    def generate_turn_image(
        self,
        save_id: str,
        turn_id: int,
        narrative_text: str,
        location_desc: str = "",
        character_desc: str = "",
        game_state_tag: str = "",
        cfg: AppConfig | None = None,
        llm: Any = None,
    ) -> Path | None:
        from mods.axiom.illustrations.image_generator import ImageGenerator

        config = cfg or axiom_config.load_config()
        if not getattr(config, "image_generation_enabled", False):
            return None

        try:
            img_gen = ImageGenerator(config, llm=llm)
            visual_prompt = img_gen.generate_prompt(
                narrative_text=narrative_text,
                location_desc=location_desc,
                character_desc=character_desc,
                game_state_tag=game_state_tag,
            )
            assets_dir = self._root_for(save_id) / "assets" / save_id
            filename = f"turn_{turn_id}.png"
            return img_gen.generate_image(visual_prompt, assets_dir, filename)
        except Exception as exc:
            logger.warning("[axiom.illustrations] Image generation failed: %s", exc)
            return None

    def truncate_assets(self, save_id: str, last_kept_turn_id: int, data_root: Path | None = None) -> int:
        """Delete PNG assets with turn_id > last_kept_turn_id."""
        assets_dir = self._root_for(save_id, data_root) / "assets" / save_id
        return truncate_assets_in(assets_dir, last_kept_turn_id)

    def fork_assets(self, src_save_id: str, dst_save_id: str, at_turn: int) -> int:
        """Copy the illustrations of turns <= at_turn to the forked save."""
        import re
        import shutil

        root = self._root_for(src_save_id)
        src = root / "assets" / src_save_id
        if not src.is_dir():
            return 0
        dst = root / "assets" / dst_save_id
        copied = 0
        for f in src.glob("turn_*.png"):
            m = re.fullmatch(r"turn_(\d+)\.png", f.name)
            if m and int(m.group(1)) <= at_turn:
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst / f.name)
                copied += 1
        self.remember_root(dst_save_id, root)
        return copied


_SERVICE: IllustrationsService | None = None


def get_illustrations_service() -> IllustrationsService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = IllustrationsService()
    return _SERVICE


def build_illustrations_prompt_section(ctx: Any) -> dict[str, str] | None:
    """Slot contribution to axiom.turn:prompt_sections (optional visual framing note)."""
    return None


def on_after_step(ctx: Any, mod_ctx: ModContext | None = None) -> None:
    """Hook: axiom.step:after_step.
    Extracts visual descriptions and schedules image generation post-commit.
    """
    # Read at call time (not bound at import): the current settings apply.
    config = axiom_config.load_config()
    if not getattr(config, "image_generation_enabled", False):
        return

    save_id = getattr(ctx, "save_id", "")
    turn_id = getattr(ctx, "turn_id", 0)
    narrative = getattr(ctx, "narrative_text", "")
    if not save_id or not narrative:
        return

    svc = get_illustrations_service()
    svc.remember_root(save_id, getattr(ctx, "data_root", None))
    location_desc = getattr(ctx, "location_desc", "")
    character_desc = getattr(ctx, "character_desc", "")
    game_state_tag = getattr(ctx, "game_state_tag", "exploration")
    llm = getattr(ctx, "llm", None)

    def _generate() -> None:
        try:
            img_path = svc.generate_turn_image(
                save_id=save_id,
                turn_id=turn_id,
                narrative_text=narrative,
                location_desc=location_desc,
                character_desc=character_desc,
                game_state_tag=game_state_tag,
                cfg=config,
                llm=llm,
            )
            if hasattr(ctx, "image_path"):
                ctx.image_path = img_path
            if hasattr(ctx, "result") and ctx.result is not None:
                ctx.result.image_path = img_path
        except Exception as exc:
            logger.warning("[axiom.illustrations] Post-commit image task failed: %s", exc)


    if hasattr(ctx, "write_batch") and hasattr(ctx.write_batch, "post_commit_callbacks"):
        ctx.write_batch.post_commit_callbacks.append(_generate)
    elif mod_ctx is not None:
        mod_ctx.spawn_job(_generate, name="axiom.illustrations:generate")  # stopped with the mod
    else:
        _generate()


def init(ctx: ModContext) -> None:
    """Entry point for axiom.illustrations mod."""
    svc = get_illustrations_service()

    # 1. Register service
    ctx.register_service("illustrations", svc)

    # 2. Register hook
    ctx.register_hook("axiom.step:after_step", lambda turn_ctx: on_after_step(turn_ctx, ctx))

    # 3. Register prompt section contribution
    ctx.contribute_slot("axiom.turn:prompt_sections", build_illustrations_prompt_section)

    # 4. External store (turn images): truncated by the engine after the SQL
    # rewind is committed; unregistered when the mod is disabled.
    ctx.register_storage(
        "assets",
        rewind_callback=lambda conn, sid, t: svc.truncate_assets(sid, t),
        fork_callback=lambda conn, src, dst, t: svc.fork_assets(src, dst, t),
    )

    # 5. Register settings tab contribution
    try:
        from mods.axiom.illustrations.ui.image_settings_tab import ImageSettingsTab
        ctx.contribute_slot("axiom.ui.qt:settings_tab", ImageSettingsTab)
    except Exception as exc:
        logger.debug("[axiom.illustrations] Could not load ImageSettingsTab: %s", exc)

