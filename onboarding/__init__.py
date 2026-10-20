"""AZ 首次启动引导：检查 AZ Home 下的 .env 是否完整，缺项时交互式补全。"""

from onboarding.wizard import ensure_env_configured

__all__ = ["ensure_env_configured"]
