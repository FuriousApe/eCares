"""Single entrypoint for the one-image-many-roles container.

`ROLE` picks which service's `main()` runs. Each service owns its own
`main.py` under `services/<name>/`; this file is only the dispatch table.
"""

from __future__ import annotations

import sys

from libs.common.settings import get_settings

_ROLE_ENTRYPOINTS = {
    "data-service": "services.data_service.main",
    "worklist-api": "services.worklist_api.main",
    "engine": "services.engine.main",
    "scheduler": "services.scheduler.main",
    "sync": "services.sync.main",
}


def main() -> None:
    role = get_settings().role
    module_path = _ROLE_ENTRYPOINTS.get(role)
    if module_path is None:
        print(f"Unknown ROLE={role!r}. Valid roles: {sorted(_ROLE_ENTRYPOINTS)}", file=sys.stderr)
        raise SystemExit(1)

    import importlib

    module = importlib.import_module(module_path)
    module.main()


if __name__ == "__main__":
    main()
