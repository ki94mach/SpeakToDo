"""Centralized logging configuration for the application."""

import logging
import sys


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


def setup_logging(log_file: str = 'speaktodo_bot.log', level: int = logging.INFO) -> logging.Logger:
    """
    Configure application-wide logging with Unicode support.
    
    Args:
        log_file: Path to the log file
        level: Logging level (default: INFO)
        
    Returns:
        Root logger instance
    """
    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Create handlers
    file_handler = logging.FileHandler(log_file, encoding='utf-8', errors='replace')
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

