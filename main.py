"""
交互式客户端程序
等待用户输入，在输入内容后加上"！"并返回给用户
生成期间按 Ctrl-C 取消本轮；等待输入时按 Ctrl-C 退出程序
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from config.settings import load_settings
from core.context.session_id import normalize_session_id


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动交互式 agent 客户端")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("cli", "web"),
        default="cli",
        help="启动模式：cli（默认）或 web",
    )
    parser.add_argument(
        "--resume",
        metavar="SESSION_ID",
        help="恢复指定 session id 的输入历史和消息历史",
    )
    parser.add_argument(
        "--project-path",
        help="当前 session 绑定的项目目录；不传时默认使用当前工作目录",
    )
    parser.add_argument(
        "--az-home",
        help="AZ 数据与配置目录；不传时使用 AZ_HOME 或 ~/.az",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Web 服务监听地址")
    parser.add_argument("--port", type=int, default=8000, help="Web 服务监听端口")
    return parser.parse_args(argv)


def _load_az_env(az_home_override: str | None) -> Path:
    """Load the .env file stored under the resolved AZ home directory."""
    raw_home = az_home_override or os.environ.get("AZ_HOME", "~/.az")
    az_home = Path(raw_home).expanduser()
    if not az_home.is_absolute():
        az_home = Path.cwd() / az_home
    az_home = az_home.resolve()

    load_dotenv(az_home / ".env")
    # The config file location must be stable. Do not let a value inside that file
    # redirect the active home after it has already been selected.
    os.environ["AZ_HOME"] = str(az_home)
    return az_home


def _configure_frozen_runtime() -> None:
    """Apply PyInstaller-only compatibility settings before importing Pydantic AI."""
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir is not None and str(bundle_dir) not in sys.path:
            # PyInstaller stores copied ``*.dist-info`` metadata under this
            # directory. Add it to the metadata search path before Pydantic AI
            # imports genai-prices and asks importlib.metadata for its version.
            sys.path.append(str(bundle_dir))
        # Logfire's generic Pydantic plugin reads Python source with inspect,
        # which is unavailable for modules inside PyInstaller's archive. AZ
        # continues to enable its explicit Pydantic AI instrumentation later.
        os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "logfire-plugin")


def main():
    """主函数：处理用户输入并返回带感叹号的内容"""
    _configure_frozen_runtime()
    args = _parse_args()
    # 在读取模型、MCP、skills 等配置前，先从 AZ Home 加载 .env。
    _load_az_env(args.az_home)
    settings = load_settings()
    if args.mode == "web":
        from interfaces.http.server import run_web

        run_web(
            settings=settings,
            host=args.host,
            port=args.port,
            default_project_path=args.project_path,
        )
        return

    from ui.cli.runner import run_cli

    session_id, resumed = normalize_session_id(args.resume)

    try:
        asyncio.run(
            run_cli(
                settings=settings,
                session_id=session_id,
                requested_project_path=args.project_path,
                resumed=resumed,
            )
        )
        # asyncio.run(server_run())

    except KeyboardInterrupt:
        # 捕获 Ctrl-C 信号
        print(f"\n\n程序已退出，再见！当前 session: {session_id}")
    except EOFError:
        # 捕获 EOF 信号（某些终端环境）
        print(f"\n\n程序已退出，再见！当前 session: {session_id}")


if __name__ == "__main__":
    main()
