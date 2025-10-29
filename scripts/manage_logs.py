#!/usr/bin/env python3
"""
Log Management Script

This script helps you manage log files:
- View log file sizes
- Clean up old logs
- Export logs for analysis
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.log_cleanup import cleanup_old_logs, get_log_size, format_size
from core import config
from core.logging import setup_logging

logger = setup_logging()


def view_log_sizes():
    """Display log file sizes."""
    total_size, file_sizes = get_log_size(config.LOG_FILE)
    
    print("\n" + "="*60)
    print("📊 Log File Sizes")
    print("="*60)
    
    if not file_sizes:
        print("No log files found.")
        return
    
    for file_path, size in sorted(file_sizes.items(), key=lambda x: x[1], reverse=True):
        file_name = Path(file_path).name
        print(f"  {file_name:30s} {format_size(size):>12s}")
    
    print("-"*60)
    print(f"  {'Total':30s} {format_size(total_size):>12s}")
    print("="*60 + "\n")


def cleanup_logs(backup_count: int = None, max_age_days: int = None):
    """Clean up old log files."""
    if backup_count is None:
        backup_count = config.LOG_BACKUP_COUNT
    
    print("\n" + "="*60)
    print("🧹 Cleaning Up Log Files")
    print("="*60)
    
    deleted_count = cleanup_old_logs(
        config.LOG_FILE,
        backup_count=backup_count,
        max_age_days=max_age_days
    )
    
    if deleted_count > 0:
        print(f"\n✅ Deleted {deleted_count} old log file(s).")
    else:
        print("\n✅ No log files to delete (all within limits).")
    
    print("="*60 + "\n")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Manage SpeakToDo log files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View log file sizes
  python scripts/manage_logs.py --view

  # Clean up old logs (keep only 3 backups)
  python scripts/manage_logs.py --cleanup --backup-count 3

  # Delete logs older than 30 days
  python scripts/manage_logs.py --cleanup --max-age-days 30

  # View sizes and cleanup in one go
  python scripts/manage_logs.py --view --cleanup
        """
    )
    
    parser.add_argument(
        '--view',
        action='store_true',
        help='View log file sizes'
    )
    
    parser.add_argument(
        '--cleanup',
        action='store_true',
        help='Clean up old log files'
    )
    
    parser.add_argument(
        '--backup-count',
        type=int,
        default=None,
        help=f'Number of backup files to keep (default: {config.LOG_BACKUP_COUNT} from config)'
    )
    
    parser.add_argument(
        '--max-age-days',
        type=int,
        default=None,
        help='Delete log files older than this many days'
    )
    
    args = parser.parse_args()
    
    if not args.view and not args.cleanup:
        # Default: show sizes
        view_log_sizes()
        return
    
    if args.view:
        view_log_sizes()
    
    if args.cleanup:
        cleanup_logs(
            backup_count=args.backup_count,
            max_age_days=args.max_age_days
        )


if __name__ == "__main__":
    main()

