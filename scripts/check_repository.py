"""检查仓库自有文件、现行文档链接、依赖声明和迁移配对；不读取被忽略的本机数据。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".go", ".ts", ".js", ".vue", ".css", ".html", ".md", ".json", ".yaml", ".yml", ".sql", ".toml", ".txt"}
RUNTIME_PARTS = {"node_modules", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "volumes"}
SECRET_NAMES = {".env", ".env.production", "id_rsa", "id_ed25519"}


def project_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, capture_output=True, check=True,
    )
    return sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})


def check_paths(paths: list[str]) -> list[str]:
    errors = []
    seen: dict[str, str] = {}
    for name in paths:
        path = Path(name)
        key = name.casefold()
        if key in seen and seen[key] != name:
            errors.append(f"{name}: 与 {seen[key]} 大小写冲突，无法跨平台检出")
        seen[key] = name
        if path.name in SECRET_NAMES or RUNTIME_PARTS.intersection(path.parts):
            errors.append(f"{name}: 密钥或运行产物不得进入仓库")
    return errors


def check_markdown(path: Path, text: str) -> list[str]:
    # 归档和 dated 审计引用的是当时布局，不把历史路径伪装成现行入口。
    if "archive" in path.parts or path.name in {"00-audit.md", "01-current-architecture.md", "timestamp-audit.md", "WORKLOG.md"}:
        return []
    text = re.sub(r"```[\s\S]*?```", "", text)
    errors = []
    for target in re.findall(r"\]\(([^\s)]+)\)", text):
        if re.match(r"(?:[a-zA-Z][\w+.-]*:|#)", target):
            continue
        target = unquote(target.split("#", 1)[0].strip("<>"))
        if not target or any(char in target for char in "*<>"):
            continue
        if not (path.parent / target).exists():
            errors.append(f"{path}: 文档链接不存在：{target}")
    return errors


def check_dependencies(root: Path) -> list[str]:
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    groups = {"dependencies": project["dependencies"], **project.get("optional-dependencies", {})}
    errors = []
    for group, deps in groups.items():
        seen = set()
        for dep in deps:
            match = re.match(r"[A-Za-z0-9_.-]+", dep)
            if not match:
                errors.append(f"pyproject.toml: {group} 依赖名称不可识别")
                continue
            key = re.sub(r"[-_.]+", "-", match[0]).lower()
            if key in seen:
                errors.append(f"pyproject.toml: {group} 重复依赖 {key}")
            seen.add(key)
    package = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))["packages"][""]
    for group in ("dependencies", "devDependencies"):
        if package.get(group, {}) != lock.get(group, {}):
            errors.append(f"frontend/package-lock.json: {group} 与 package.json 不一致")
    return errors


def check_migrations(root: Path) -> list[str]:
    migrations = root / "server/migrations"
    up = {p.name.removesuffix(".up.sql") for p in migrations.glob("*.up.sql")}
    down = {p.name.removesuffix(".down.sql") for p in migrations.glob("*.down.sql")}
    errors = [f"server/migrations: {name} 缺少成对的 up/down" for name in sorted(up ^ down)]
    versions: set[str] = set()
    for name in sorted(up):
        match = re.fullmatch(r"(\d{6})_[a-z][a-z0-9_]*", name)
        if not match:
            errors.append(f"server/migrations/{name}: 必须使用六位版本号与 snake_case 名称")
        elif match[1] in versions:
            errors.append(f"server/migrations/{name}: 迁移版本重复")
        else:
            versions.add(match[1])
    return errors


def run(root: Path = ROOT) -> tuple[int, list[str]]:
    paths = project_files(root)
    errors = check_paths(paths)
    for name in paths:
        path = root / name
        if not path.is_file() or (path.suffix not in TEXT_SUFFIXES and path.name != "AGENTS.md"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{name}: 文本必须使用 UTF-8")
            continue
        if "\x00" in text or text.startswith("\ufeff"):
            errors.append(f"{name}: 文本不得含 NUL 或 UTF-8 BOM")
        if path.suffix == ".md":
            errors.extend(check_markdown(path, text))
    errors.extend(check_dependencies(root))
    errors.extend(check_migrations(root))
    return len(paths), errors


def main() -> int:
    try:
        count, errors = run()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"[repository] 无法完成检查：{type(exc).__name__}", file=sys.stderr)
        return 2
    for error in errors:
        print(f"[repository] {error}")
    print(f"[repository] 已检查 {count} 个自有文件，问题 {len(errors)} 条")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
