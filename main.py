import asyncio
import random
import signal
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

from config import Config
from database.mongodb import db_client
from database.models import User, MessageRole, Message
from graph.therapy_graph import TherapyGraph
from utils.logger import logger

class TherapyBot:
    """Main therapy bot class"""
    
    def __init__(self):
        self.app = None
        self.therapy_graph = TherapyGraph()
        self.user_states = {}  # Track user conversation states
        self.is_running = False
        
    async def initialize(self):
        """Initialize the bot"""
        try:
            # Validate configuration
            Config.validate()
            
            # Create application
            self.app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
            
            # Add handlers
            self.app.add_handler(CommandHandler("start", self.start_command))
            self.app.add_handler(CommandHandler("help", self.help_command))
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            # Error handler
            self.app.add_error_handler(self.error_handler)
            
            logger.info("Bot initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize bot", error=e)
            raise
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        user_id = str(user.id)
        
        try:
            logger.log_user_interaction(user_id, "START_COMMAND")
            
            # Get or create user in database
            db_user = await db_client.get_user(user_id)
            if not db_user:
                db_user = await db_client.create_user(
                    user_id=user_id,
                    first_name=user.first_name,
                    username=user.username
                )
                logger.info(f"New user created: {user_id}")
            
            # Increment session count
            await db_client.increment_session_count(user_id)
            
            # Welcome message
            welcome_message = (
                f"سلام {user.first_name}! 👋\n\n"
                "من یک دستیار درمانی هستم که اینجا هستم تا به شما کمک کنم.\n"
                "می‌توانید با من در مورد احساسات، مشکلات یا هر چیزی که در ذهنتان است صحبت کنید.\n\n"
                "من مثل یک انسان واقعی پاسخ می‌دهم و گاهی ممکن است سوالاتی از شما بپرسم تا بهتر بتوانم کمکتان کنم.\n\n"
                "برای شروع، چطور احساس می‌کنید؟ 🤔"
            )
            
            await update.message.reply_text(welcome_message)
            
            # Initialize user state
            self.user_states[user_id] = {
                'conversation_active': True,
                'last_message_time': asyncio.get_event_loop().time(),
                'waiting_for_response': False
            }
            
        except Exception as e:
            logger.error("Error in start command", user_id, e)
            await update.message.reply_text(
                "متأسفانه خطایی رخ داده است. لطفاً دوباره تلاش کنید."
            )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        user_id = str(update.effective_user.id)
        
        try:
            logger.log_user_interaction(user_id, "HELP_COMMAND")
            
            help_message = (
                "🤖 **راهنمای استفاده از ربات درمانی**\n\n"
                "**دستورات موجود:**\n"
                "/start - شروع گفتگو با ربات\n"
                "/help - نمایش این راهنما\n\n"
                "**نحوه استفاده:**\n"
                "• فقط با من صحبت کنید، مثل یک دوست واقعی\n"
                "• من ممکن است سوالاتی از شما بپرسم\n"
                "• صادقانه پاسخ دهید تا بتوانم بهتر کمکتان کنم\n"
                "• تمام گفتگوهای شما محرمانه و امن هستند\n\n"
                "**نکته مهم:**\n"
                "من یک دستیار هوش مصنوعی هستم و جایگزین مشاوره حرفه‌ای نیستم. "
                "در مواقع اضطراری، لطفاً با متخصصان واقعی تماس بگیرید.\n\n"
                "آماده‌ام تا به شما کمک کنم! 😊"
            )
            
            await update.message.reply_text(help_message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error("Error in help command", user_id, e)
            await update.message.reply_text(
                "متأسفانه خطایی رخ داده است. لطفاً دوباره تلاش کنید."
            )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user messages"""
        user = update.effective_user
        user_id = str(user.id)
        message_text = update.message.text
        
        try:
            logger.log_user_interaction(user_id, "MESSAGE", message_text[:100])
            
            # Check if user exists
            db_user = await db_client.get_user(user_id)
            if not db_user:
                await update.message.reply_text(
                    "لطفاً ابتدا دستور /start را اجرا کنید."
                )
                return
            
            # Check if bot is waiting for response (to prevent spam)
            if self.user_states.get(user_id, {}).get('waiting_for_response', False):
                await update.message.reply_text(
                    "لطفاً کمی صبر کنید، دارم پیام شما را بررسی می‌کنم... 🤔"
                )
                return
            
            # Set waiting state
            if user_id not in self.user_states:
                self.user_states[user_id] = {}
            self.user_states[user_id]['waiting_for_response'] = True
            
            # Show typing indicator
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
            
            # Add human-like delay
            delay = random.uniform(Config.RESPONSE_DELAY_MIN, Config.RESPONSE_DELAY_MAX)
            await asyncio.sleep(delay)
            
            # Process message through therapy graph
            try:
                # Create or get active conversation
                if user_id not in self.user_states or 'conversation_id' not in self.user_states[user_id]:
                    conversation_id = await db_client.create_conversation(user_id)
                    if user_id not in self.user_states:
                        self.user_states[user_id] = {}
                    self.user_states[user_id]['conversation_id'] = conversation_id

                conversation_id = self.user_states[user_id]['conversation_id']

                # Process message through therapy graph
                response = await self.therapy_graph.process_message(user_id, message_text, conversation_id)
                
                # Send response
                await update.message.reply_text(response["response"])

                # Handle follow-up questions ONLY if it's NOT already included in response
                if (response.get("requires_follow_up") and 
                    response.get("follow_up_question") and 
                    response.get("follow_up_question") not in response["response"]):
                    
                    # Add small delay before follow-up
                    await asyncio.sleep(1)
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
                    await asyncio.sleep(2)
                    
                    await update.message.reply_text(response["follow_up_question"])
                
                logger.info(f"Response sent to user {user_id}")
                
            except Exception as e:
                logger.error("Error processing message through therapy graph", user_id, e)
                
                # Fallback response
                fallback_responses = [
                    "متأسفانه در حال حاضر نمی‌توانم به خوبی پاسخ دهم. می‌توانید سوال خود را دوباره مطرح کنید؟",
                    "ببخشید، کمی مشکل فنی داشتم. لطفاً دوباره تلاش کنید.",
                    "در حال حاضر کمی مشکل دارم. می‌توانید کمی بعد دوباره امتحان کنید؟"
                ]
                
                await update.message.reply_text(random.choice(fallback_responses))
            
        except Exception as e:
            logger.error("Error handling message", user_id, e)
            await update.message.reply_text(
                "متأسفانه خطایی رخ داده است. لطفاً دوباره تلاش کنید."
            )
        
        finally:
            # Clear waiting state
            if user_id in self.user_states:
                self.user_states[user_id]['waiting_for_response'] = False
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle telegram errors"""
        user_id = None
        if update and update.effective_user:
            user_id = str(update.effective_user.id)
        
        logger.error("Telegram error occurred", user_id, context.error)
        
        # Try to send error message to user
        if update and update.message:
            try:
                await update.message.reply_text(
                    "متأسفانه خطایی رخ داده است. لطفاً دوباره تلاش کنید."
                )
            except TelegramError:
                pass  # Can't send message, just log
    
    async def start_polling(self):
        """Start the bot with polling"""
        try:
            self.is_running = True
            logger.info("Starting bot with polling...")
            
            # Initialize the application properly
            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling(drop_pending_updates=True)
            
            # Keep the bot running
            while self.is_running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error("Error during polling", error=e)
            raise
        finally:
            await self.stop_polling()
    
    async def stop_polling(self):
        """Stop the bot polling"""
        try:
            self.is_running = False
            if self.app:
                await self.app.updater.stop()
                await self.app.stop()
                await self.app.shutdown()
        except Exception as e:
            logger.error("Error stopping polling", error=e)
    
    async def shutdown(self):
        """Shutdown the bot gracefully"""
        try:
            logger.info("Shutting down bot...")
            
            # Stop polling first
            await self.stop_polling()
            
            # Close database connection
            db_client.close()
            
            logger.info("Bot shutdown completed")
            
        except Exception as e:
            logger.error("Error during shutdown", error=e)

# Global bot instance
bot_instance = None

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print(f"\nReceived signal {signum}. Shutting down gracefully...")
    if bot_instance:
        asyncio.create_task(bot_instance.shutdown())
    sys.exit(0)

async def main():
    """Main function"""
    global bot_instance
    bot_instance = TherapyBot()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize bot
        await bot_instance.initialize()
        
        # Start polling
        await bot_instance.start_polling()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error("Fatal error", error=e)
        raise
    finally:
        await bot_instance.shutdown()

if __name__ == "__main__":
    try:
        # Use asyncio.run properly
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        logger.error("Fatal error in main", error=e)