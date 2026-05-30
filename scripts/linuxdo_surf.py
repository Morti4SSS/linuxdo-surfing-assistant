from pathlib import Path
import importlib.util
import sys


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "tools" / "linuxdo_surf.py"


def _load_helper():
    spec = importlib.util.spec_from_file_location("linuxdo_surf_state_helper", HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None) -> int:
    helper = _load_helper()
    return helper.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
