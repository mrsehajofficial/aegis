"""
Logging configuration for Aegis.

Sets up both console and file logging with rotation.
"""
import logging
import sys
from pathlib import Path
from app.config.settings import settings


def setup_logging() -> None:
    """
    Configure application-wide logging.
    
    - Console handler for all levels
    - File handler (rotating) for INFO and above
    - SQLAlchemy and Alembic loggers set to WARN by default
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    # Ensure logs directory exists
    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    # Create formatters
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove any existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    try:
        from logging.handlers import RotatingFileHandler
        
        log_file = logs_dir / "aegis.log"
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        # Fall back to basic file logging if rotation fails
        logging.warning(f"Could not set up rotating file handler: {e}")
    
    # Reduce noise from third-party libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.INFO)
    logging.getLogger("telegram").setLevel(logging.WARNING)
