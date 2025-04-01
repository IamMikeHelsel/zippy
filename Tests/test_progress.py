# Tests/test_progress.py
"""
Tests for the progress tracking and reporting functionality.
"""

import pytest
import time
import threading
from unittest.mock import MagicMock
from src.progress import ProgressTracker, ProgressFormat, create_cli_progress_bar


def test_progress_tracker_initialization():
    """Test that the ProgressTracker initializes with expected default values."""
    tracker = ProgressTracker(operation_name="Test Operation")

    assert tracker.operation_name == "Test Operation"
    assert tracker.update_interval == 0.1
    assert tracker.format == ProgressFormat.STANDARD
    assert tracker.last_percentage == -1
    assert isinstance(tracker._cancel_event, threading.Event)
    assert len(tracker.callbacks) == 0


def test_callback_registration():
    """Test registering, using, and unregistering callbacks."""
    tracker = ProgressTracker()

    # Create a mock callback
    mock_callback = MagicMock()

    # Register the callback
    tracker.register_callback("test", mock_callback)
    assert "test" in tracker.callbacks

    # Update progress should invoke the callback
    tracker.update(50, 100)
    mock_callback.assert_called_once_with(50, 100)

    # Unregister the callback
    tracker.unregister_callback("test")
    assert "test" not in tracker.callbacks

    # After unregistering, updates should not call the callback
    mock_callback.reset_mock()
    tracker.update(75, 100)
    mock_callback.assert_not_called()


def test_progress_update_rate_limiting():
    """Test that progress updates are rate-limited."""
    tracker = ProgressTracker(update_interval=0.5)

    # Register a mock callback
    mock_callback = MagicMock()
    tracker.register_callback("test", mock_callback)

    # First update always happens
    tracker.update(10, 100)
    assert mock_callback.call_count == 1
    mock_callback.reset_mock()

    # Immediate second update should be skipped due to rate limiting
    tracker.update(11, 100)
    assert mock_callback.call_count == 0

    # Update with the same percentage should be skipped
    time.sleep(0.6)  # Wait for rate limit to expire
    tracker.update(10, 100)  # Still 10% (10/100)
    assert mock_callback.call_count == 0

    # Update with different percentage after interval should happen
    tracker.update(20, 100)
    assert mock_callback.call_count == 1
    mock_callback.reset_mock()

    # Final update to 100% should always happen
    tracker.update(100, 100)
    assert mock_callback.call_count == 1


def test_multiple_callbacks():
    """Test that multiple callbacks are all invoked."""
    tracker = ProgressTracker()

    # Create multiple mock callbacks
    callback1 = MagicMock()
    callback2 = MagicMock()
    callback3 = MagicMock()

    # Register all callbacks
    tracker.register_callback("cb1", callback1)
    tracker.register_callback("cb2", callback2)
    tracker.register_callback("cb3", callback3)

    # Update progress
    tracker.update(50, 100)

    # All callbacks should be called with the same values
    callback1.assert_called_once_with(50, 100)
    callback2.assert_called_once_with(50, 100)
    callback3.assert_called_once_with(50, 100)


def test_progress_formatting():
    """Test the different progress formatting options."""
    # Test MINIMAL format
    tracker = ProgressTracker(format=ProgressFormat.MINIMAL)
    result = tracker.format_progress_info(50, 100)
    assert result == "50%"

    # Test STANDARD format (default)
    tracker = ProgressTracker()
    result = tracker.format_progress_info(1536, 4096)
    assert "50%" in result
    assert "1.5 KB" in result
    assert "4.0 KB" in result

    # Test DETAILED format
    tracker = ProgressTracker(format=ProgressFormat.DETAILED)
    tracker.start_time = time.time() - 2  # Set start time to 2 seconds ago
    result = tracker.format_progress_info(1048576, 2097152)  # 1MB of 2MB
    assert "50%" in result
    assert "1.0 MB/2.0 MB" in result
    assert "MB/s" in result  # Speed
    assert "ETA" in result  # Estimated time remaining


def test_reset_and_cancel():
    """Test the reset and cancel functionality."""
    tracker = ProgressTracker()

    # Update progress to change last_percentage
    tracker.update(50, 100)
    assert tracker.last_percentage == 50

    # Reset should restore initial state
    tracker.reset()
    assert tracker.last_percentage == -1
    assert not tracker.is_cancelled

    # Test cancellation
    tracker.cancel()
    assert tracker.is_cancelled
    assert tracker._cancel_event.is_set()

    # Get cancel event
    cancel_event = tracker.get_cancel_event()
    assert isinstance(cancel_event, threading.Event)
    assert cancel_event.is_set()


def test_cli_progress_bar():
    """Test the CLI progress bar generator."""
    progress_bar = create_cli_progress_bar(width=20, filled_char="#", empty_char="-")

    # Test empty progress bar (0%)
    result = progress_bar(0, 100)
    assert result == "[--------------------] 0%"

    # Test half-filled progress bar (50%)
    result = progress_bar(50, 100)
    assert result == "[##########----------] 50%"

    # Test full progress bar (100%)
    result = progress_bar(100, 100)
    assert result == "[####################] 100%"

    # Test with default characters
    default_bar = create_cli_progress_bar(width=10)
    result = default_bar(30, 100)
    assert result == "[███-------] 30%"


def test_error_handling_in_callbacks():
    """Test that errors in callbacks don't crash the progress tracker."""
    tracker = ProgressTracker()

    # Create callbacks - one that works and one that raises an exception
    good_callback = MagicMock()

    def bad_callback(current, total):
        raise Exception("Test error in callback")

    # Register both callbacks
    tracker.register_callback("good", good_callback)
    tracker.register_callback("bad", bad_callback)

    # Update should not crash despite the bad callback
    tracker.update(50, 100)

    # Good callback should still be called
    good_callback.assert_called_once_with(50, 100)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
