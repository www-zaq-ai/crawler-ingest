"""Prove that an omitted required transitive package fails a clean locked install."""

from importlib import metadata
from pathlib import Path
import subprocess
import tempfile
import sys


ROOT = Path(__file__).resolve().parents[1]
OMITTED = "urllib3"


def main():
    if not any(
        requirement.lower().startswith(OMITTED)
        for requirement in metadata.requires("requests") or []
    ):
        raise RuntimeError("requests no longer requires urllib3; choose another active dependency")

    lines = (ROOT / "requirements.lock").read_text().splitlines(keepends=True)
    retained = [line for line in lines if not line.startswith(f"{OMITTED}==")]
    if len(retained) != len(lines) - 1:
        raise RuntimeError("expected exactly one urllib3 lock entry")

    with tempfile.TemporaryDirectory(prefix="incomplete-crawler-lock-", dir=ROOT) as directory:
        base = Path(directory)
        lock = base / "requirements.lock"
        lock.write_text("".join(retained))
        subprocess.run([sys.executable, "-m", "venv", str(base / "venv")], check=True)
        python = base / "venv" / "bin" / "python"

        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-deps", "-r", str(lock)],
            check=True,
        )
        check = subprocess.run(
            [str(python), "-m", "pip", "check"], capture_output=True, text=True
        )
        missing = subprocess.run(
            [str(python), "-m", "pip", "show", OMITTED], capture_output=True
        )
        if check.returncode == 0 or OMITTED not in check.stdout.lower():
            raise RuntimeError(f"incomplete lock unexpectedly passed pip check: {check.stdout}")
        if missing.returncode == 0:
            raise RuntimeError(f"pip installed omitted dependency {OMITTED}")

    print("Incomplete lock failed pip check without installing urllib3, as expected.")


if __name__ == "__main__":
    main()
