import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Configuration settings for the therapy bot"""
    
    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    # OpenRouter AI Configuration
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    AI_MODEL = "deepseek/deepseek-r1-0528:free"
    SITE_URL = os.getenv('SITE_URL', 'http://localhost')
    SITE_NAME = os.getenv('SITE_NAME', 'Therapy Bot')
    
    # MongoDB Configuration
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'therapy_bot')
    
    # Collections
    USERS_COLLECTION = 'users'
    CONVERSATIONS_COLLECTION = 'conversations'
    MEMORY_COLLECTION = 'memory'
    
    # Memory Management
    SHORT_TERM_MEMORY_LIMIT = 50  # Number of recent messages to keep in short-term
    LONG_TERM_MEMORY_THRESHOLD = 0.7  # Importance score threshold for long-term storage
    
    # Personality Analysis
    PERSONALITY_UPDATE_THRESHOLD = 10  # Update personality after N messages
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = 'logs/bot.log'
    
    # Bot Behavior
    RESPONSE_DELAY_MIN = 2  # Minimum delay in seconds (human-like behavior)
    RESPONSE_DELAY_MAX = 5  # Maximum delay in seconds
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        required_vars = [
            'TELEGRAM_BOT_TOKEN',
            'OPENROUTER_API_KEY',
            'MONGODB_URI'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True