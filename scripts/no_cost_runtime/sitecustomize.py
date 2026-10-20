"""Automatically install the guard before any project module is imported."""

import os

try:
    from guard import install

    install()
except BaseException:
    # Python normally swallows sitecustomize errors: fail closed instead.
    os._exit(78)
