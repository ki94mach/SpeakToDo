"""File utility functions."""

import os
import logging

logger = logging.getLogger(__name__)


def cleanup_temp_file(file_path: str) -> None:
    """
    Safely remove a temporary file if it exists.
    
    Args:
        file_path: Path to the file to remove
    """
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.debug(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            logger.warning(f"Could not remove temporary file {file_path}: {e}")

