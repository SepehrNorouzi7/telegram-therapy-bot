import logging
import os
from datetime import datetime
from config import Config

class BotLogger:
    """Custom logger for the therapy bot"""
    
    def __init__(self):
        self.logger = logging.getLogger('therapy_bot')
        self.setup_logger()
    
    def setup_logger(self):
        """Setup logging configuration"""
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Set logging level
        level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
        self.logger.setLevel(level)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # File handler
        file_handler = logging.FileHandler(Config.LOG_FILE, encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        
        # Add handlers
        if not self.logger.handlers:
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)
    
    def info(self, message, user_id=None):
        """Log info message"""
        if user_id:
            message = f"[User:{user_id}] {message}"
        self.logger.info(message)
    
    def error(self, message, user_id=None, error=None):
        """Log error message"""
        if user_id:
            message = f"[User:{user_id}] {message}"
        if error:
            message = f"{message} - Error: {str(error)}"
        self.logger.error(message)
    
    def warning(self, message, user_id=None):
        """Log warning message"""
        if user_id:
            message = f"[User:{user_id}] {message}"
        self.logger.warning(message)
    
    def debug(self, message, user_id=None):
        """Log debug message"""
        if user_id:
            message = f"[User:{user_id}] {message}"
        self.logger.debug(message)
    
    def log_user_interaction(self, user_id, action, details=None):
        """Log user interactions"""
        message = f"User interaction - Action: {action}"
        if details:
            message += f" - Details: {details}"
        self.info(message, user_id)
    
    def log_ai_request(self, user_id, model, tokens_used=None):
        """Log AI service requests"""
        message = f"AI Request - Model: {model}"
        if tokens_used:
            message += f" - Tokens: {tokens_used}"
        self.info(message, user_id)
    
    def log_database_operation(self, operation, collection, user_id=None):
        """Log database operations"""
        message = f"DB Operation - {operation} on {collection}"
        self.info(message, user_id)

# Global logger instance
logger = BotLogger()