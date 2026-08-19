import argparse
import re
import sys

from cryptography.fernet import Fernet

from .admin_auth import AdminAuthService
from .config import get_settings
from .database import Database
from .errors import ApiError


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="控制台管理员离线维护工具")
    subcommands = parser.add_subparsers(dest="command", required=True)

    create = subcommands.add_parser("create", help="创建唯一的初始超级管理员")
    create.add_argument("--username", required=True)
    create.add_argument("--display-name", required=True)

    reset = subcommands.add_parser("reset-password", help="重置指定管理员密码并撤销其全部会话")
    reset.add_argument("--username", required=True)
    reset_totp = subcommands.add_parser("reset-totp", help="清除超级管理员TOTP并撤销其全部会话")
    reset_totp.add_argument("--username", required=True)
    subcommands.add_parser("generate-totp-key", help="生成用于加密TOTP密钥的Fernet主密钥")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "generate-totp-key":
        print(Fernet.generate_key().decode("ascii"))
        return 0
    username = arguments.username.strip()
    if not USERNAME_PATTERN.fullmatch(username):
        print("错误：用户名必须为 3-64 位英文、数字、点、下划线或短横线", file=sys.stderr)
        return 2

    settings = get_settings()
    database = Database(settings.database_path)
    database.initialize()
    service = AdminAuthService(database, settings)
    try:
        if arguments.command == "create":
            display_name = arguments.display_name.strip()
            if not display_name or len(display_name) > 64:
                print("错误：显示名称必须为 1-64 个字符", file=sys.stderr)
                return 2
            user, initial_password = service.create_initial_super_admin(username, display_name)
        elif arguments.command == "reset-password":
            user, initial_password = service.reset_password_from_cli(username)
        else:
            user = service.reset_totp_from_cli(username)
            print(f"管理员：{user['username']} ({user['role']})")
            print("TOTP二次验证已清除，全部旧会话已撤销；下次登录必须重新绑定。")
            return 0
    except ApiError as error:
        print(f"错误：{error.message}", file=sys.stderr)
        return 1

    print(f"管理员：{user['username']} ({user['role']})")
    print(f"一次性初始密码：{initial_password}")
    print("请妥善保存；该密码不会再次显示，首次登录后必须立即修改。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
