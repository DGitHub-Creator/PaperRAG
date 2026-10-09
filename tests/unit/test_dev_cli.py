"""`scripts/dev.py` 的单元级验证（P0-0）。

真跑 `up/migrate` 需要 Docker，属 real 级；这里只锁住不依赖容器的部分：
命令面、.env 解析、以及 doctor 对密钥 fail-fast 的判定。
"""

import importlib.util
import sys
from pathlib import Path

DEV_PATH = Path(__file__).resolve().parents[2] / "scripts" / "dev.py"

SUBCOMMANDS = ("doctor", "up", "down", "ps", "logs", "migrate", "test")


def _load_dev():
    spec = importlib.util.spec_from_file_location("dev_cli", DEV_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dev = _load_dev()


class TestCommandSurface:
    def test_documented_subcommands_are_exposed(self):
        help_text = dev.build_parser().format_help()
        for name in SUBCOMMANDS:
            assert f"{name}  " in help_text, f"dev.py 缺少 {name} 子命令"

    def test_test_subcommand_passes_args_through_to_pytest(self, monkeypatch):
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["cmd"] = cmd
            return 0

        monkeypatch.setattr(dev, "run", fake_run)

        def invoke(argv):
            args = dev.build_parser().parse_args(argv)
            return args.func(args)

        assert invoke(["test", "-m", "unit"]) == 0
        assert seen["cmd"] == [sys.executable, "-m", "pytest", "-m", "unit", "-q"]

        assert invoke(["test", "--", "-k", "auth", "-v"]) == 0
        assert seen["cmd"] == [sys.executable, "-m", "pytest", "-k", "auth", "-v"]


class TestEnvFileParsing:
    def test_comments_and_quotes_are_ignored(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text('# c\nJWT_SECRET_KEY= "abc123" \n\nEMPTY=\nAPP_ENV=production\n', encoding="utf-8")
        env = dev.read_env_file(f)
        assert env["JWT_SECRET_KEY"] == "abc123"
        assert env["APP_ENV"] == "production"
        assert env["EMPTY"] == ""

    def test_doctor_blocks_on_empty_or_placeholder_secret(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(dev.shutil, "which", lambda name: "/usr/bin/docker")
        monkeypatch.setattr(dev, "_exec_ok", lambda cmd: True)
        env = tmp_path / ".env"
        monkeypatch.setattr(dev, "ENV_FILE", env)

        for value in ("", "dev-only-insecure-jwt-secret"):
            env.write_text(f"JWT_SECRET_KEY={value}\n", encoding="utf-8")
            capsys.readouterr()
            assert dev.cmd_doctor(None) == 1
            assert "JWT_SECRET_KEY" in capsys.readouterr().out
