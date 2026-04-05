import os
import sys
from .base import (
    get_model_container_path, get_legacy_db_path,
    read_manifest, get_db_alto_version
)
from .v0_1a.loader import LoaderV0_1a
from .v0_2a.loader import LoaderV0_2a

_LOADERS = {
    "0.1a": LoaderV0_1a(),
    "0.2a": LoaderV0_2a(),
}
_DEFAULT_LOADER = LoaderV0_2a()

def get_loader(model_name: str):
    container_path = get_model_container_path(model_name)
    if container_path and os.path.isfile(container_path):
        manifest = read_manifest(container_path)
        if manifest:
            version = manifest.get("alto_version")
            if version and version in _LOADERS:
                return _LOADERS[version]
            else:
                print(f"⚠️ Unknown container version '{version}', using latest loader", file=sys.stderr)
                return _DEFAULT_LOADER
    legacy_path = get_legacy_db_path(model_name)
    if legacy_path and os.path.isfile(legacy_path):
        version = get_db_alto_version(legacy_path)
        if version and version in _LOADERS:
            return _LOADERS[version]
        else:
            print(f"⚠️ Unknown legacy version '{version}', using latest loader", file=sys.stderr)
            return _DEFAULT_LOADER
    raise FileNotFoundError(f"Model '{model_name}' not found")