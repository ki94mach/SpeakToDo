"""Log file cleanup utility."""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def cleanup_old_logs(
    log_file: str,
    backup_count: int,
    max_age_days: Optional[int] = None
) -> int:
    """
    Manually cleanup old log files.
    
    Args:
        log_file: Path to the main log file
        backup_count: Maximum number of backup files to keep
        max_age_days: Optional: delete logs older than this many days
        
    Returns:
        Number of files deleted
    """
    deleted_count = 0
    log_path = Path(log_file)
    log_dir = log_path.parent if log_path.parent != Path('.') else Path('.')
    
    # Find all log files (main + rotated backups)
    log_pattern = log_path.stem
    log_ext = log_path.suffix
    
    # Get all matching files
    log_files = sorted(
        [f for f in log_dir.glob(f"{log_pattern}*{log_ext}") if f.is_file()],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    
    # Keep only the specified number of backups
    if len(log_files) > backup_count:
        files_to_delete = log_files[backup_count:]
        
        for file_to_delete in files_to_delete:
            try:
                file_to_delete.unlink()
                deleted_count += 1
                logger.info(f"Deleted old log file: {file_to_delete}")
            except Exception as e:
                logger.warning(f"Could not delete {file_to_delete}: {e}")
    
    # Optional: Delete files older than max_age_days
    if max_age_days:
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        
        for log_file_path in log_files:
            try:
                file_time = datetime.fromtimestamp(log_file_path.stat().st_mtime)
                if file_time < cutoff_date:
                    log_file_path.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted old log file (older than {max_age_days} days): {log_file_path}")
            except Exception as e:
                logger.warning(f"Could not check/delete {log_file_path}: {e}")
    
    return deleted_count


def get_log_size(log_file: str) -> tuple[int, dict[str, int]]:
    """
    Get the size of log files.
    
    Args:
        log_file: Path to the main log file
        
    Returns:
        Tuple of (total_size_bytes, dict of file_sizes)
    """
    log_path = Path(log_file)
    log_dir = log_path.parent if log_path.parent != Path('.') else Path('.')
    
    log_pattern = log_path.stem
    log_ext = log_path.suffix
    
    # Get all matching files
    log_files = [f for f in log_dir.glob(f"{log_pattern}*{log_ext}") if f.is_file()]
    
    file_sizes = {}
    total_size = 0
    
    for log_file_path in log_files:
        size = log_file_path.stat().st_size
        file_sizes[str(log_file_path)] = size
        total_size += size
    
    return total_size, file_sizes


def format_size(size_bytes: int) -> str:
    """Format size in bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

