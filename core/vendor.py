from __future__ import annotations

import os
import site
import sys
import importlib.util
from types import ModuleType
from pathlib import Path


def vendor_root() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    default_vendor_root = project_root / ".betto" / "vendor"
    return Path(os.environ.get("BETTO_VENDOR_DIR", default_vendor_root)).resolve()


def active_vendor_dir() -> Path:
    root = vendor_root()
    versioned_vendor = root / f"py{sys.version_info.major}{sys.version_info.minor}"
    return versioned_vendor if versioned_vendor.exists() else root


def should_use_vendor() -> bool:
    if "BETTO_VENDOR_DIR" in os.environ:
        return True
    return sys.platform == "win32"


def add_vendor_path() -> None:
    if not should_use_vendor():
        return
    root = vendor_root()
    vendor_dir = active_vendor_dir()
    candidates = [vendor_dir]
    if vendor_dir != root:
        candidates.append(root)
    for vendor_dir in candidates:
        if not vendor_dir.exists():
            continue
        vendor_path = str(vendor_dir)
        if vendor_path not in sys.path:
            sys.path.insert(0, vendor_path)
        site.addsitedir(vendor_path)


def load_vendor_package(package_name: str) -> ModuleType:
    if not should_use_vendor():
        raise ImportError(f"vendored packages are disabled on {sys.platform}")
    add_vendor_path()
    package_dir = active_vendor_dir() / package_name
    init_path = package_dir / "__init__.py"
    if not init_path.exists():
        raise ImportError(f"{package_name} is not installed in {active_vendor_dir()}")

    for loaded_name in list(sys.modules):
        if loaded_name == package_name or loaded_name.startswith(f"{package_name}."):
            del sys.modules[loaded_name]

    spec = importlib.util.spec_from_file_location(
        package_name,
        init_path,
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {package_name} from {init_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return module
