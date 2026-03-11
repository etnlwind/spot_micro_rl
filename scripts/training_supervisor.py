"""Compatibility wrapper for the legacy v1 supervisor."""

import os
import sys

if __package__:
    from .v1.training_supervisor import *  # type: ignore # noqa: F401,F403
    from .v1.training_supervisor import main as _legacy_main  # type: ignore
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    from v1.training_supervisor import *  # noqa: F401,F403
    from v1.training_supervisor import main as _legacy_main


if __name__ == "__main__":
    _legacy_main()
