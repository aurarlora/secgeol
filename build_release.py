from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import shutil


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

PLUGIN_NAME = "secgeol"
VERSION = "1.0.0"

ROOT = Path(__file__).resolve().parent
BUILD_DIR = ROOT / "release"
STAGING_DIR = BUILD_DIR / PLUGIN_NAME
ZIP_FILE = BUILD_DIR / f"SecGeol-{VERSION}.zip"

DIRECTORIES = [
    "core",
    "i18n",
    "resources",
]

FILES = [
    "__init__.py",
    "icon.png",
    "LICENSE",
    "metadata.txt",
    "README.md",
    "secgeol.py",
    "secgeol_dialog.py",
    "secGeol.ui",
]

EXCLUDED_NAMES = {
    "__pycache__",
    ".DS_Store",
}

EXCLUDED_PREFIXES = (
    "._",
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def excluded(path: Path) -> bool:
    """Return True when a file or directory must not enter the release."""
    if path.name in EXCLUDED_NAMES:
        return True

    if path.name.startswith(EXCLUDED_PREFIXES):
        return True

    return "__pycache__" in path.parts


def sha256(path: Path) -> str:
    """Calculate the SHA-256 hash of a file."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest().upper()


# ---------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------

def main() -> None:
    print(f"Building SecGeol {VERSION}...")

    # Clean previous build.
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)

    STAGING_DIR.mkdir(parents=True)

    # Copy directories.
    for directory in DIRECTORIES:
        source = ROOT / directory
        destination = STAGING_DIR / directory

        if not source.exists():
            raise FileNotFoundError(f"Missing required directory: {source}")

        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                ".DS_Store",
                "._*",
            ),
        )

    # Copy root files.
    for filename in FILES:
        source = ROOT / filename

        if not source.exists():
            raise FileNotFoundError(f"Missing required file: {source}")

        shutil.copy2(source, STAGING_DIR / filename)

    # Create ZIP.
    #
    # Directory entries are written explicitly. This is important because
    # QGIS on macOS expects a valid plugin root directory inside the archive.
    with ZipFile(ZIP_FILE, "w", ZIP_DEFLATED) as archive:

        archive.writestr(f"{PLUGIN_NAME}/", "")

        for path in sorted(STAGING_DIR.rglob("*")):
            if path.is_dir() and not excluded(path):
                relative = path.relative_to(STAGING_DIR).as_posix()
                archive.writestr(f"{PLUGIN_NAME}/{relative}/", "")

        for path in sorted(STAGING_DIR.rglob("*")):
            if path.is_file() and not excluded(path):
                relative = path.relative_to(STAGING_DIR).as_posix()
                archive.write(
                    path,
                    arcname=f"{PLUGIN_NAME}/{relative}",
                )

    digest = sha256(ZIP_FILE)

    print()
    print("Release created successfully.")
    print(f"ZIP    : {ZIP_FILE}")
    print(f"SHA256 : {digest}")


if __name__ == "__main__":
    main()