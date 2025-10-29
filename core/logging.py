"""Centralized logging configuration for the application."""

import logging
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path


class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler that safely handles Unicode characters on Windows by catching encoding errors."""
    
    def emit(self, record):
        """Emit a record, handling Unicode encoding errors gracefully."""
        try:
            msg = self.format(record)
            stream = self.stream
            # Try to write with the original stream encoding
            stream.write(msg + self.terminator)
            self.flush()
        except UnicodeEncodeError:
            # If encoding fails, try to replace problematic characters
            try:
                msg = self.format(record)
                # Replace emoji and other problematic Unicode with safe alternatives
                safe_msg = msg.encode('ascii', 'replace').decode('ascii')
                stream.write(safe_msg + self.terminator)
                self.flush()
            except Exception:
                # If all else fails, just write a simplified message
                try:
                    stream.write(f"LOG: {record.levelname} - {record.name}: [Unicode message truncated]\n")
                    self.flush()
                except Exception:
                    # Silently fail if we can't write at all
                    self.handleError(record)
        except Exception:
            self.handleError(record)


def setup_logging(
    log_file: str = 'logs/speaktodo_bot.log',
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB default
    backup_count: int = 5,  # Keep 5 backup files
    use_timed_rotation: bool = False,  # Use time-based rotation instead
    when: str = 'midnight',  # For timed rotation: 'D' (daily), 'W0' (weekly), 'H' (hourly), 'midnight'
    interval: int = 1  # For timed rotation: interval between rotations
) -> logging.Logger:
    """
    Configure application-wide logging with Unicode support and automatic log rotation.
    
    Args:
        log_file: Path to the log file
        level: Logging level (default: INFO)
        max_bytes: Maximum size in bytes before rotation (default: 10MB). Ignored if use_timed_rotation=True
        backup_count: Number of backup files to keep (default: 5)
        use_timed_rotation: If True, use time-based rotation instead of size-based (default: False)
        when: For timed rotation: 'D' (daily), 'W0' (weekly), 'H' (hourly), 'midnight' (default: 'midnight')
        interval: Interval between rotations for timed rotation (default: 1)
        
    Returns:
        Root logger instance
    """
    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Ensure log directory exists
    log_path = Path(log_file)
    log_dir = log_path.parent
    
    # Create logs directory if it doesn't exist
    if not log_dir.exists():
        log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create file handler with rotation
    if use_timed_rotation:
        # Time-based rotation (e.g., daily, weekly)
        file_handler = TimedRotatingFileHandler(
            log_file,
            when=when,
            interval=interval,
            backupCount=backup_count,
            encoding='utf-8',
            errors='replace'
        )
        # Add suffix for timed rotation
        file_handler.suffix = '%Y-%m-%d' if when == 'midnight' or when == 'D' else '%Y-%m-%d_%H-%M-%S'
    else:
        # Size-based rotation (default)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8',
            errors='replace'
        )
    
    # Create console handler
    console_handler = SafeStreamHandler(sys.stdout)
    
    # Set formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return logging.getLogger(__name__)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)

