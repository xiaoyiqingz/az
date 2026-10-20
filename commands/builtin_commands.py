"""
内置命令处理模块

提供常用的内置命令处理功能，分为两种类型：
1. 直接处理型：如 /exit、/help - 直接执行并等待用户继续输入
2. 转换型：如 /time、/date - 将命令转换为用户输入传给 agent
"""

from typing import Optional, Tuple
from enum import Enum


SLASH_COMMAND_DESCRIPTIONS = {
    "/help": "显示命令帮助",
    "/exit": "退出程序",
    "/quit": "退出程序",
    "/q": "退出程序",
    "/version": "显示版本信息",
    "/clear": "清屏",
    "/model": "切换模型（/model <deepseek|qwen|mimo|ollama>）",
    "/time": "查询当前时间",
    "/date": "查询当前日期",
    "/weather": "查询天气和穿衣建议",
}


def get_slash_command_descriptions() -> dict[str, str]:
    """Return CLI slash commands and their completion descriptions."""
    return dict(SLASH_COMMAND_DESCRIPTIONS)


class CommandType(Enum):
    """命令类型枚举"""

    DIRECT = "direct"  # 直接处理型
    CONVERT = "convert"  # 转换型
    NONE = "none"  # 非内置命令


def process_builtin_command(
    user_input: str, session_id: str | None = None
) -> Tuple[bool, Optional[str], CommandType]:
    """
    处理内置命令

    Args:
        user_input: 用户输入的字符串

    Returns:
        Tuple[bool, Optional[str], CommandType]:
            - 第一个值表示是否处理了内置命令（True表示已处理，False表示未处理）
            - 第二个值表示处理结果（直接处理型返回显示内容，转换型返回转换后的用户输入）
            - 第三个值表示命令类型
    """
    # 去除首尾空格并转换为小写
    command = user_input.strip().lower()

    # 直接处理型命令（执行后等待用户继续输入）
    direct_commands = {
        "/exit": _handle_exit,
        "/quit": _handle_exit,
        "/q": _handle_exit,
        "/help": _handle_help,
        "/version": _handle_version,
        "/clear": _handle_clear,
    }

    # 转换型命令（转换为用户输入传给 agent）
    convert_commands = {
        "/time": _convert_time,
        "/date": _convert_date,
        "/weather": _convert_weather,
    }

    # 检查直接处理型命令
    if command in direct_commands:
        if command in {"/exit", "/quit", "/q"}:
            is_processed, result = _handle_exit(session_id)
        else:
            is_processed, result = direct_commands[command]()
        return is_processed, result, CommandType.DIRECT

    # 检查转换型命令
    if command in convert_commands:
        is_processed, result = convert_commands[command]()
        return is_processed, result, CommandType.CONVERT

    # 不是内置命令
    return False, None, CommandType.NONE


def _handle_exit(session_id: str | None = None) -> Tuple[bool, None]:
    """处理退出命令
    
    注意：不再直接调用 sys.exit(0)，而是返回标记让调用者处理退出逻辑
    这样可以确保在退出前保存历史记录等清理工作
    """
    if session_id:
        print(f"程序即将退出，再见！当前 session: {session_id}")
    else:
        print("程序即将退出，再见！")
    # 不再直接调用 sys.exit(0)，让调用者处理退出逻辑
    return True, None


def _convert_time() -> Tuple[bool, str]:
    """转换时间查询命令为用户输入"""
    return True, "请告诉我当前时间是"


def _convert_date() -> Tuple[bool, str]:
    """转换日期查询命令为用户输入"""
    return True, "请告诉我今天的日期是"


def _convert_weather() -> Tuple[bool, str]:
    """转换天气查询命令为用户输入"""
    return True, "请告诉我今天的天气情况，并给我一些穿衣建议"


def _handle_help() -> Tuple[bool, str]:
    """处理帮助命令"""
    help_text = """
可用命令:

直接处理型命令（执行后等待用户继续输入）:
  /exit /quit /q  - 退出程序
  /help            - 显示此帮助信息
  /version         - 显示版本信息
  /clear           - 清屏
  /model [名称]     - 切换模型，未配置的模型会引导补全配置

转换型命令（转换为用户输入传给 AI）:
  /time            - 查询当前时间并获取相关信息
  /date            - 查询当前日期并获取历史信息
  /weather         - 查询天气并获取穿衣建议
    """
    return True, help_text.strip()


def _handle_version() -> Tuple[bool, str]:
    """处理版本查询命令"""
    return True, "内置命令处理器 v1.0.0"


def _handle_clear() -> Tuple[bool, str]:
    """处理清屏命令"""
    import os

    os.system("cls" if os.name == "nt" else "clear")
    return True, "屏幕已清空"


def is_builtin_command(user_input: str) -> bool:
    """
    检查输入是否为内置命令

    Args:
        user_input: 用户输入的字符串

    Returns:
        bool: 如果是内置命令返回True，否则返回False
    """
    command = user_input.strip().lower()
    builtin_commands = {
        # 直接处理型命令
        "/exit",
        "/quit",
        "/q",
        "/help",
        "/version",
        "/clear",
        # 转换型命令
        "/time",
        "/date",
        "/weather",
    }
    return command in builtin_commands


def get_command_type(user_input: str) -> CommandType:
    """
    获取命令类型

    Args:
        user_input: 用户输入的字符串

    Returns:
        CommandType: 命令类型
    """
    command = user_input.strip().lower()

    direct_commands = {"/exit", "/quit", "/q", "/help", "/version", "/clear"}
    convert_commands = {"/time", "/date", "/weather"}

    if command in direct_commands:
        return CommandType.DIRECT
    elif command in convert_commands:
        return CommandType.CONVERT
    else:
        return CommandType.NONE
