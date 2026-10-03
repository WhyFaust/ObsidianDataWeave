"""Run with the project Python: tests/check_install_config.py (no installation)."""

import shutil
import sys
import tempfile
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install


def main():
    original_root = install.ROOT
    try:
        with tempfile.TemporaryDirectory() as temporary:
            install.ROOT = Path(temporary)
            shutil.copy2(original_root / "config.example.toml", install.ROOT)
            vault = install.ROOT / "Wiki с пробелами и 'кавычками'"
            vault.mkdir()
            install.create_config(str(vault), 'remote"example')
            config_path = install.ROOT / "config.toml"
            with config_path.open("rb") as stream:
                config = tomllib.load(stream)
            assert config["vault"]["vault_path"] == vault.resolve().as_posix()
            assert config["rclone"]["remote"] == 'remote"example:'
            assert Path(config["rclone"]["staging_dir"]).is_absolute()
            original = config_path.read_bytes()
            install.create_config("different-vault", "different-remote")
            assert config_path.read_bytes() == original, "existing config changed"
    finally:
        install.ROOT = original_root
    print("Installer config check passed.")


if __name__ == "__main__":
    main()
