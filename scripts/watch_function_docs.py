"""Watch project files and regenerate functionality docs automatically."""

from __future__ import annotations

import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from scripts.generate_function_docs import main as generate_docs

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WATCH_PATHS = [
    PROJECT_ROOT / "services",
    PROJECT_ROOT / "common",
    PROJECT_ROOT / "web-app" / "src",
    PROJECT_ROOT / "prompts",
    PROJECT_ROOT / "docs" / "openapi.yaml",
]
WATCH_SUFFIXES = {".py", ".vue", ".ts", ".md", ".yaml", ".yml"}


class DocRefreshHandler(FileSystemEventHandler):
    """Regenerate the functionality doc when tracked files change."""

    def __init__(self) -> None:
        self._last_run = 0.0

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Trigger regeneration on create/update/delete/move events."""

        if event.is_directory:
            return

        src_path = Path(event.src_path)
        if src_path.suffix not in WATCH_SUFFIXES:
            return

        now = time.time()
        if now - self._last_run < 1.0:
            return

        self._last_run = now
        print(f"[watch] detected change: {src_path}")
        generate_docs()


def main() -> None:
    """Start the file watcher for functionality docs."""

    observer = Observer()
    handler = DocRefreshHandler()

    for path in WATCH_PATHS:
        if path.is_file():
            observer.schedule(handler, str(path.parent), recursive=False)
        else:
            observer.schedule(handler, str(path), recursive=True)

    generate_docs()
    observer.start()
    print("Watching files for functionality document updates...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()
