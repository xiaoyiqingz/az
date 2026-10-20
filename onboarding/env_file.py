"""读取与补全 AZ Home 下的 .env 文件。

写入只发生在 ``az_home/.env``：临时文件建在同一目录内再原子替换，
不经过系统临时目录，也不跟随符号链接写到 AZ Home 之外。
"""

from __future__ import annotations

import io
import os
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values
from dotenv.parser import parse_stream

ENV_FILE_NAME = ".env"


def env_file_path(az_home: Path) -> Path:
    if not az_home.is_absolute():
        raise ValueError(f"AZ Home 必须是绝对路径：{az_home}")
    return az_home / ENV_FILE_NAME


def read_env_file(env_path: Path) -> dict[str, str]:
    """只读取文件本身的值，不受进程环境变量影响。"""
    if not env_path.is_file():
        return {}
    return {key: value or "" for key, value in dotenv_values(env_path).items()}


def write_env_values(az_home: Path, updates: Mapping[str, str]) -> Path:
    """逐项更新或追加键值，保留原有注释与其他配置，返回写入的文件路径。"""
    env_path = env_file_path(az_home)
    if env_path.is_symlink():
        raise SystemExit(f"{env_path} 是符号链接，为避免写到 AZ Home 之外，已拒绝修改。")
    if env_path.exists() and not env_path.is_file():
        raise SystemExit(f"{env_path} 不是普通文件，已拒绝修改。")

    az_home.mkdir(parents=True, exist_ok=True)
    original = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    content = _render(original, updates)

    # 临时文件与 .env 同目录，保证 os.replace 是原子替换。
    fd, temp_name = tempfile.mkstemp(dir=az_home, prefix=".env.", suffix=".tmp")
    try:
        # 只设置刚创建的临时文件的权限，使替换后的 .env 权限与原来一致，
        # 不会对 .env 或任何其他路径执行 chmod。
        os.fchmod(fd, _preserved_mode(env_path))
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            temp_file.write(content)
        os.replace(temp_name, env_path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return env_path


def _preserved_mode(env_path: Path) -> int:
    """已有 .env 沿用原权限；新建时与普通文件一样遵循 umask。"""
    if env_path.exists():
        return stat.S_IMODE(env_path.stat().st_mode)
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def _render(original: str, updates: Mapping[str, str]) -> str:
    remaining = dict(updates)
    lines: list[str] = []
    for binding in parse_stream(io.StringIO(original)):
        if binding.key in remaining:
            lines.append(f"{binding.key}={remaining.pop(binding.key)}\n")
        else:
            lines.append(binding.original.string)
    if lines and not lines[-1].endswith("\n"):
        lines.append("\n")
    lines += [f"{key}={value}\n" for key, value in remaining.items()]
    return "".join(lines)
