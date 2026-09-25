"""Checks for the resolved application dependencies used by ZAQ."""

from importlib import metadata, util
from pathlib import Path

from packaging.requirements import Requirement


ROOT = Path(__file__).resolve().parents[1]
EXTRAS = ("docx", "pptx", "xlsx", "xls")
BACKENDS = ("mammoth", "pandas", "openpyxl", "xlrd", "pptx", "PIL", "imagehash")


def requirements(path):
    return [
        Requirement(line)
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_direct_requirements_are_pinned_in_lock():
    lock = ROOT / "requirements.lock"
    assert lock.is_file()
    pins = {requirement.name.lower(): requirement for requirement in requirements(lock)}

    for direct in requirements(ROOT / "requirements.txt"):
        assert direct.name.lower() in pins
        assert pins[direct.name.lower()].specifier == direct.specifier


def test_locked_dependencies_and_format_extras_are_installed():
    for locked in requirements(ROOT / "requirements.lock"):
        if locked.marker and not locked.marker.evaluate({"extra": ""}):
            continue
        assert metadata.version(locked.name) in locked.specifier

    for extra in EXTRAS:
        for declaration in metadata.requires("markitdown") or []:
            dependency = Requirement(declaration)
            if dependency.marker and dependency.marker.evaluate({"extra": extra}):
                assert metadata.version(dependency.name) in dependency.specifier

    for backend in BACKENDS:
        assert util.find_spec(backend) is not None
