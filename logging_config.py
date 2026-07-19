import logging
import logging.handlers
import os
import re
import filelock


def configure_logging(
    process_name: str = "main",
    app_log_max_bytes: int = 5 * 1024 * 1024,
) -> None:
    """Configure logging with a size-capped app.log and console output.

    When app.log exceeds app_log_max_bytes, it is deleted and recreated.
    Uses RotatingFileHandler with backupCount=0 (no .1/.2 files).

    Example:
        >>> configure_logging(process_name="worker-0")
    """
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        f"%(asctime)s [{process_name}] %(name)s %(levelname)s %(message)s"
    )

    # Console
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    # app.log — rotating with backupCount=0 (delete and recreate on overflow)
    app_handler = logging.handlers.RotatingFileHandler(
        "app.log",
        maxBytes=app_log_max_bytes,
        backupCount=0,
        encoding="utf-8",
    )
    app_handler.setFormatter(formatter)
    root_logger.addHandler(app_handler)


class DisgramLogWriter:
    """Process-safe writer for Disgram.log (message link tracking).

    Automatically triggers cleanup when the file exceeds max_bytes,
    preserving latest message links, WARNING entries, and ERROR entries.
    Informational messages (e.g. 'Bot working for...') are discarded.

    Example:
        >>> writer = DisgramLogWriter()
        >>> writer.append("2024-01-01 12:00:00 New message: https://t.me/channel/123")
    """

    _PRESERVE_PATTERNS = ("WARNING", "ERROR", "CRITICAL")

    def __init__(self, path: str = "Disgram.log", max_bytes: int = 5 * 1024 * 1024) -> None:
        self._path = path
        self._max_bytes = max_bytes
        self._lock = filelock.FileLock(f"{path}.lock")

    def append(self, entry: str) -> None:
        """Append an entry, triggering cleanup if file exceeds size limit."""
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
            self._check_and_cleanup()

    def _check_and_cleanup(self) -> None:
        """If file exceeds max_bytes, preserve latest links + WARNING/ERROR entries.

        Discards purely informational lines (e.g. 'Bot working for channel...').
        """
        try:
            if os.path.getsize(self._path) <= self._max_bytes:
                return
        except OSError:
            return

        header_line = None
        latest_messages: dict[str, int] = {}
        preserved_lines: list[str] = []

        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                if "Add your message links" in stripped:
                    header_line = stripped
                    continue

                # Track latest message link per channel
                matches = re.findall(r"https://t\.me/([^/\s]+)/(\d+)", stripped)
                for channel, msg_num in matches:
                    num = int(msg_num)
                    if channel not in latest_messages or num > latest_messages[channel]:
                        latest_messages[channel] = num

                # Preserve WARNING/ERROR/CRITICAL lines
                if any(level in stripped for level in self._PRESERVE_PATTERNS):
                    preserved_lines.append(stripped)

        channel_links = [
            f"https://t.me/{ch}/{num}"
            for ch, num in sorted(latest_messages.items())
        ]

        with open(self._path, "w", encoding="utf-8") as f:
            if header_line:
                f.write(f"{header_line}\n")
            for link in channel_links:
                f.write(f"{link}\n")
            for line in preserved_lines:
                f.write(f"{line}\n")

    def is_message_logged(self, channel: str, number: int) -> bool:
        """Check if a message number has been logged for the given channel."""
        with self._lock:
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    for line in f:
                        match = re.search(rf"https://t.me/{channel}/(\d+)", line)
                        if match and int(match.group(1)) >= number:
                            return True
            except FileNotFoundError:
                pass
            return False
