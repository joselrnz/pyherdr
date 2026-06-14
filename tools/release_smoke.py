from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VERSION_CHECK = (
    "import importlib.metadata as m, pyherdr; "
    "assert m.version('pyherdr') == pyherdr.__version__, "
    "f\"metadata={m.version('pyherdr')} package={pyherdr.__version__}\""
)


def venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def pyherdr_script(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/pyherdr.exe" if sys.platform == "win32" else "bin/pyherdr")


def build_smoke_commands(repo_root: Path, venv_dir: Path, python: str) -> list[list[str]]:
    venv_py = venv_python(venv_dir)
    pyherdr = pyherdr_script(venv_dir)
    return [
        [python, "-m", "venv", str(venv_dir)],
        [str(venv_py), "-m", "pip", "install", str(repo_root)],
        [str(venv_py), "-c", VERSION_CHECK],
        [str(venv_py), "-m", "pyherdr", "--version"],
        [str(pyherdr), "--version"],
        [str(pyherdr), "headless", "status"],
    ]


def run_smoke(repo_root: Path, work_dir: Path, *, python: str = sys.executable, dry_run: bool = False) -> None:
    repo_root = repo_root.resolve()
    work_dir = work_dir.resolve()
    venv_dir = work_dir / "release-smoke-venv"
    if venv_dir.exists() and not dry_run:
        shutil.rmtree(venv_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    commands = build_smoke_commands(repo_root, venv_dir, python)
    for command in commands:
        print("+ " + " ".join(command))
        if not dry_run:
            subprocess.run(command, cwd=repo_root, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install PyHerdr into a clean venv and launch the installed CLI.")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--dry-run", action="store_true", help="print commands without creating a venv")
    args = parser.parse_args(argv)

    if args.work_dir is not None:
        run_smoke(args.repo, args.work_dir, python=args.python, dry_run=args.dry_run)
        return 0

    with tempfile.TemporaryDirectory(prefix="pyherdr-release-smoke-") as temp:
        run_smoke(args.repo, Path(temp), python=args.python, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
