# src/progress.py
"""
Provides progress reporting functionality for both GUI and CLI interfaces.

This module centralizes progress tracking and reporting to maintain consistent
behavior across different interfaces while avoiding code duplication.
"""

import time
import sys
import threading
from typing import Callable, Optional, Dict, Union, Any
from enum import Enum


class ProgressFormat(Enum):
    """Format options for progress display."""

    MINIMAL = 1  # Just percentage
    STANDARD = 2  # Percentage and size info
    DETAILED = 3  # Percentage, size, speed, and ETA


class ProgressTracker:
    """
    Track and report operation progress with consistent behavior.

    This class provides a unified way to track progress for both GUI and CLI
    applications, handling rate-limiting and format conversions.

    Attributes:
        start_time (float): Time when progress tracking started
        update_interval (float): Minimum seconds between progress updates
        last_update_time (float): Time of the last progress update
        last_percentage (int): Previously reported progress percentage
        format (ProgressFormat): The level of detail in progress reports
        operation_name (str): Name of the current operation for reports
        callbacks (Dict): Dictionary of registered callback functions
    """

    def __init__(
        self,
        operation_name: str = "Processing",
        update_interval: float = 0.1,
        format: ProgressFormat = ProgressFormat.STANDARD,
    ):
        """
        Initialize a new progress tracker.

        Args:
            operation_name: Name of the operation for progress messages
            update_interval: Minimum seconds between progress updates
            format: Level of detail to include in progress reports
        """
        self.start_time = time.time()
        self.update_interval = update_interval
        self.last_update_time = 0
        self.last_percentage = -1
        self.format = format
        self.operation_name = operation_name
        self.callbacks: Dict[str, Callable] = {}
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()

    def register_callback(self, name: str, callback: Callable[[int, int], Any]) -> None:
        """
        Register a callback function to receive progress updates.

        Args:
            name: Unique identifier for this callback
            callback: Function that accepts (current, total) parameters
        """
        with self._lock:
            self.callbacks[name] = callback

    def unregister_callback(self, name: str) -> None:
        """
        Remove a previously registered callback.

        Args:
            name: Name of the callback to remove
        """
        with self._lock:
            if name in self.callbacks:
                del self.callbacks[name]

    def update(self, current: int, total: int) -> None:
        """
        Report current progress to all registered callbacks.

        This method handles rate-limiting to avoid overwhelming the UI
        with too-frequent updates.

        Args:
            current: Current progress value
            total: Total expected value when complete
        """
        # Always update for 0% and 100%
        is_start = current == 0 and self.last_percentage == -1
        is_complete = current >= total and self.last_percentage < 100

        # Skip update if not start/complete and too soon after last update
        current_time = time.time()
        if not (is_start or is_complete):
            if current_time - self.last_update_time < self.update_interval:
                return

        # Calculate percentage
        if total > 0:
            percentage = int((current / total) * 100)
        else:
            percentage = 100 if current > 0 else 0

        # Only update if percentage changed or is start/complete
        if not (percentage != self.last_percentage or is_start or is_complete):
            return

        self.last_percentage = percentage
        self.last_update_time = current_time

        # Call all registered callbacks with updated progress
        with self._lock:
            for callback in self.callbacks.values():
                try:
                    callback(current, total)
                except Exception as e:
                    print(f"Error in progress callback: {e}", file=sys.stderr)

    def reset(self) -> None:
        """Reset progress tracker to initial state."""
        self.start_time = time.time()
        self.last_update_time = 0
        self.last_percentage = -1
        self._cancel_event.clear()

    def cancel(self) -> None:
        """Signal cancellation to operations using this tracker."""
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        """Check if operation has been cancelled."""
        return self._cancel_event.is_set()

    def get_cancel_event(self) -> threading.Event:
        """Get the cancellation event for this tracker."""
        return self._cancel_event

    def format_progress_info(self, current: int, total: int) -> str:
        """
        Format current progress into a human-readable string.

        Args:
            current: Current progress value
            total: Total expected value

        Returns:
            Formatted progress string according to current format setting
        """
        # Calculate basic metrics
        percentage = int((current / max(1, total)) * 100)
        elapsed = time.time() - self.start_time

        if self.format == ProgressFormat.MINIMAL:
            return f"{percentage}%"

        # Format file sizes
        if current < 1024:
            current_str = f"{current} B"
            total_str = f"{total} B"
        elif current < 1024 * 1024:
            current_str = f"{current/1024:.1f} KB"
            total_str = f"{total/1024:.1f} KB"
        else:
            current_str = f"{current/(1024*1024):.1f} MB"
            total_str = f"{total/(1024*1024):.1f} MB"

        if self.format == ProgressFormat.STANDARD:
            return f"{percentage}% ({current_str}/{total_str})"

        # Calculate speed and ETA for detailed format
        if elapsed > 0 and current > 0:
            speed = current / elapsed  # bytes per second
            eta = (total - current) / speed if speed > 0 else 0

            # Format speed
            if speed < 1024:
                speed_str = f"{speed:.1f} B/s"
            elif speed < 1024 * 1024:
                speed_str = f"{speed/1024:.1f} KB/s"
            else:
                speed_str = f"{speed/(1024*1024):.1f} MB/s"

            # Format time remaining
            if eta > 60:
                eta_str = f"{int(eta/60)}m {int(eta%60)}s"
            else:
                eta_str = f"{int(eta)}s"

            return f"{percentage}% ({current_str}/{total_str}) at {speed_str}, ETA: {eta_str}"
        else:
            return f"{percentage}% ({current_str}/{total_str})"


# CLI progress bar generator
def create_cli_progress_bar(
    width: int = 40, filled_char: str = "█", empty_char: str = "░"
) -> Callable[[int, int], str]:
    """
    Create a function that generates CLI progress bars.

    Args:
        width: Width of the progress bar in characters
        filled_char: Character to use for filled portion
        empty_char: Character to use for empty portion

    Returns:
        Function that accepts (current, total) and returns a progress bar string
    """

    def progress_bar(current: int, total: int) -> str:
        percentage = int((current / max(1, total)) * 100)
        filled_width = int(percentage / 100 * width)
        bar = filled_char * filled_width + empty_char * (width - filled_width)
        return f"[{bar}] {percentage}%"

    return progress_bar


# Create a global tracker for reuse
default_tracker = ProgressTracker()
