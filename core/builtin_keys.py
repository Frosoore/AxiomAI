"""
core/builtin_keys.py

Shared beta API keys + model affordability table — TICKET-062 item 2.

For the public beta, the app ships a small pool of prepaid Fireworks.ai keys
(named AXIOMAI-0..3 in the Fireworks dashboard, **they expire 2026-06-30**)
so a new tester can play without configuring anything. They are used only
when the user has not entered their own Fireworks key, and the backend
rotates to the next key automatically when one is revoked or exhausted
(`UniversalClient.fallback_api_keys`).

The keys are lightly obfuscated (reversed, then base64) so repo scrapers'
`fw_…` regexes don't match the raw text. This deters bots, not humans — the
pool is prepaid, capped and short-lived, which is the actual safety net.

Pricing: the Fireworks API does not expose prices, so a small hand-maintained
table (docs.fireworks.ai/serverless/pricing, read 2026-06-12) drives the
"affordable on the shared keys" filter. A model absent from the table is
treated as NOT affordable — a new expensive model can never slip through.
"""

from __future__ import annotations

import base64

# Master switch for the shared beta-key offering. Flip to False to RETIRE the
# "free keys for beta testers" feature (e.g. once the prepaid pool expires on
# 2026-06-30) WITHOUT deleting anything: the keys, the price table and the
# rotation logic all stay in place, ready to re-enable by flipping it back.
# When False the app behaves as if no shared pool existed — register_builtin_
# providers() and apply_beta_defaults() become no-ops, get_builtin_keys()
# stays empty, the model-affordability filter switches off, and a user with no
# key of their own simply gets the clear "add your key in Settings" message.
BUILTIN_KEYS_ENABLED: bool = True

# Reversed + base64 (see module docstring). Order = rotation order.
_OBFUSCATED_FIREWORKS_KEYS: tuple[str, ...] = (
    "WjRzMTFxNDMzNFpoOEFrVlh4d2c3V193Zg==",  # AXIOMAI-0
    "eFBXZzhZQlZYSGhnaDFmaTdxdzVCU193Zg==",  # AXIOMAI-1
    "eFFLSjZmem9WcjFFd3B6M3FwV0FRU193Zg==",  # AXIOMAI-2
    "MjhYaXpLcVk4NTl3UlpnUWV6TnVwQ193Zg==",  # AXIOMAI-3
)


def fireworks_builtin_keys() -> list[str]:
    """Decode and return the shared Fireworks key pool, in rotation order."""
    return [
        base64.b64decode(s).decode("utf-8")[::-1]
        for s in _OBFUSCATED_FIREWORKS_KEYS
    ]


# USD per 1M tokens (input, output) — serverless models verified live with a
# 1-token completion on 2026-06-12. /models does not list them all (e.g.
# gpt-oss-20b and deepseek-v4-flash answer but are absent from the listing).
FIREWORKS_MODEL_PRICES: dict[str, tuple[float, float]] = {
    "accounts/fireworks/models/gpt-oss-20b": (0.07, 0.30),
    "accounts/fireworks/models/deepseek-v4-flash": (0.14, 0.28),
    "accounts/fireworks/models/gpt-oss-120b": (0.15, 0.60),
    "accounts/fireworks/models/qwen3p6-plus": (0.50, 3.00),
    "accounts/fireworks/models/kimi-k2p5": (0.60, 3.00),
    "accounts/fireworks/models/kimi-k2p6": (0.95, 4.00),
    "accounts/fireworks/models/glm-5p1": (1.40, 4.40),
    "accounts/fireworks/models/deepseek-v4-pro": (1.74, 3.48),
}

# Affordability cap on the SHARED keys (per 1M tokens). Keeps the beta pool
# alive: gpt-oss-120b/-20b and deepseek-v4-flash pass, flagships don't.
BUILTIN_MAX_INPUT_PRICE: float = 0.30
BUILTIN_MAX_OUTPUT_PRICE: float = 1.00


def is_affordable_on_builtin(model_id: str) -> bool:
    """Whether a model may be used on the shared keys (unknown = no)."""
    prices = FIREWORKS_MODEL_PRICES.get(model_id)
    if prices is None:
        return False
    return (prices[0] <= BUILTIN_MAX_INPUT_PRICE
            and prices[1] <= BUILTIN_MAX_OUTPUT_PRICE)


def affordable_builtin_models() -> list[str]:
    """Model ids allowed on the shared keys, cheapest output first."""
    return sorted(
        (m for m in FIREWORKS_MODEL_PRICES if is_affordable_on_builtin(m)),
        key=lambda m: FIREWORKS_MODEL_PRICES[m][1],
    )


def register_builtin_providers() -> None:
    """Register the shared pools with the engine (called once at startup).

    No-op when BUILTIN_KEYS_ENABLED is False (the shared-key offering is
    retired): nothing is registered, so the app runs on user keys only.
    """
    if not BUILTIN_KEYS_ENABLED:
        return
    from axiom.config import register_builtin_keys

    register_builtin_keys("fireworks", fireworks_builtin_keys())


def apply_beta_defaults() -> None:
    """Very first launch (no settings.json yet): default the app to the
    Fireworks backend so a brand-new tester can play with zero configuration.
    The default fireworks model (AppConfig) is affordable on the shared keys.

    Existing installs (a settings file exists) are never touched. No-op when
    BUILTIN_KEYS_ENABLED is False — without a shared pool there is nothing to
    default to, so a fresh install keeps the standard backend default.
    """
    if not BUILTIN_KEYS_ENABLED:
        return
    from axiom import paths
    from axiom.config import AppConfig, save_config

    if paths.get_settings_file().exists():
        return
    save_config(AppConfig(llm_backend="fireworks"))
