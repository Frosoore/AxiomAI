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

from axiom.config import AppConfig, load_config
from axiom.kernel.context import ModContext
from axiom.logger import logger
from axiom.savestore import truncate_assets_in
from axiom.storage_registry import register_custom_storage


class IllustrationsService:
    """Public service exposed by axiom.illustrations."""

    def __init__(self, data_root: Path | None = None) -> None:
        self.data_root = data_root

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
        from axiom import paths
        try:
            from mods.axiom.illustrations.image_generator import ImageGenerator
        except (ImportError, ValueError):
            from axiom.image_generator import ImageGenerator

        config = cfg or load_config()
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
            root = self.data_root or paths._data_root()
            assets_dir = root / "assets" / save_id
            filename = f"turn_{turn_id}.png"
            return img_gen.generate_image(visual_prompt, assets_dir, filename)
        except Exception as exc:
            logger.warning("[axiom.illustrations] Image generation failed: %s", exc)
            return None

    def truncate_assets(self, save_id: str, last_kept_turn_id: int, data_root: Path | None = None) -> int:
        """Delete PNG assets with turn_id > last_kept_turn_id."""
        from axiom import paths
        root = data_root or self.data_root or paths._data_root()
        assets_dir = root / "assets" / save_id
        return truncate_assets_in(assets_dir, last_kept_turn_id)


_SERVICE: IllustrationsService | None = None


def get_illustrations_service() -> IllustrationsService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = IllustrationsService()
    return _SERVICE


def build_illustrations_prompt_section(ctx: Any) -> dict[str, str] | None:
    """Slot contribution to axiom.turn:prompt_sections (optional visual framing note)."""
    return None


def on_after_step(ctx: Any) -> None:
    """Hook: axiom.step:after_step.
    Extracts visual descriptions and schedules image generation post-commit.
    """
    config = load_config()
    if not getattr(config, "image_generation_enabled", False):
        return

    save_id = getattr(ctx, "save_id", "")
    turn_id = getattr(ctx, "turn_id", 0)
    narrative = getattr(ctx, "narrative_text", "")
    if not save_id or not narrative:
        return

    svc = get_illustrations_service()
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
    else:
        import threading
        threading.Thread(target=_generate, daemon=True).start()


def init(ctx: ModContext) -> None:
    """Entry point for axiom.illustrations mod."""
    svc = get_illustrations_service()

    # 1. Register service
    ctx.register_service("illustrations", svc)

    # 2. Register hook
    ctx.register_hook("axiom.step:after_step", on_after_step)

    # 3. Register prompt section contribution
    ctx.contribute_slot("axiom.turn:prompt_sections", build_illustrations_prompt_section)

    # 4. Register custom storage rollback with storage_registry
    try:
        register_custom_storage(
            "assets",
            rewind_callback=lambda conn, sid, t: svc.truncate_assets(sid, t),
        )
    except Exception as exc:
        logger.debug("[axiom.illustrations] Failed to register custom storage 'assets': %s", exc)

    # 5. Register settings tab contribution
    try:
        from mods.axiom.illustrations.ui.image_settings_tab import ImageSettingsTab
        ctx.contribute_slot("axiom.ui.qt:settings_tab", ImageSettingsTab)
    except Exception as exc:
        logger.debug("[axiom.illustrations] Could not load ImageSettingsTab: %s", exc)

