"""Configuration: loads from env vars first, then ~/.tasks/config.yaml fallback."""

import os
from pathlib import Path

import yaml

TASKS_DIR = Path.home() / ".tasks"
CONFIG_PATH = TASKS_DIR / "config.yaml"


def _load_yaml() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


_yaml_cache: dict | None = None


def get_config() -> dict:
    global _yaml_cache
    if _yaml_cache is None:
        _yaml_cache = _load_yaml()
    return _yaml_cache


def get_supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL") or get_config().get("supabase", {}).get("url", "")
    if not url:
        raise SystemExit(
            "Error: No Supabase URL. Set SUPABASE_URL env var or add supabase.url to ~/.tasks/config.yaml"
        )
    return url


def get_supabase_key() -> str:
    key = os.environ.get("SUPABASE_KEY") or get_config().get("supabase", {}).get("key", "")
    if not key:
        raise SystemExit(
            "Error: No Supabase key. Set SUPABASE_KEY env var or add supabase.key to ~/.tasks/config.yaml"
        )
    return key


def get_anthropic_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY") or get_config().get("anthropic_api_key", "")
    if not key:
        raise SystemExit(
            "Error: No API key. Set ANTHROPIC_API_KEY env var or add anthropic_api_key to ~/.tasks/config.yaml"
        )
    return key


def get_telegram_config() -> dict:
    return get_config().get("telegram", {})


def get_daily_hours() -> int:
    return get_config().get("daily", {}).get("available_hours", 6)


def get_vercel_url() -> str:
    return os.environ.get("VERCEL_URL") or get_config().get("vercel_url", "")
