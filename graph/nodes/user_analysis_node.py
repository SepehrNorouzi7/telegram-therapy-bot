from typing import Dict, Any, List
from database.mongodb import db_client
from database.models import User, UserAnalysisResult, Message, MessageRole, EmotionalState
from ai_services.memory_manager import memory_manager
from ai_services.personality_analyzer import personality_analyzer
from graph.state import TherapyState
from utils.logger import logger

class UserAnalysisNode:
    """Node 1: Analyzes user information and characteristics"""
    
    def __init__(self):
        self.emotion_keywords = {
            'خوشحال': 'happy',
            'شاد': 'happy',
            'خوب': 'happy',
            'ناراحت': 'sad',
            'غمگین': 'sad',
            'افسرده': 'sad',
            'عصبانی': 'angry',
            'عصبی': 'angry',
            'خشمگین': 'angry',
            'نگران': 'anxious',
            'مضطرب': 'anxious',
            'ترسیده': 'anxious',
            'آرام': 'calm',
            'راحت': 'calm',
            'هیجان': 'excited',
            'هیجان‌زده': 'excited'
        }
    
    async def execute(self, state: TherapyState) -> Dict[str, Any]:
        """Execute user analysis"""
        
        try:
            user_id = state["user_id"]  # Changed from state.user_id
            current_message = state["current_message"]  # Changed from state.current_message
            
            logger.debug("Starting user analysis", user_id)
            
            # Get or create user
            user = await self._get_or_create_user(user_id)
            
            # Get conversation context from memory
            memory_context = await memory_manager.get_relevant_context(
                user_id, current_message
            )
            
            # Detect emotional state
            emotional_state = self._detect_emotional_state(current_message)
            
            # Get recent conversation for personality analysis
            recent_conversations = await db_client.get_recent_conversations(user_id, limit=3)
            recent_messages = []
            for conv in recent_conversations:
                recent_messages.extend(conv.messages)
            
            # Add current message to analysis
            current_msg = Message(
                role=MessageRole.USER,
                content=current_message,
                emotion_detected=emotional_state
            )
            recent_messages.append(current_msg)
            
            # Update personality if needed
            personality_insights = {}
            if await personality_analyzer.should_update_personality(user_id, len(recent_messages)):
                updated_personality = await personality_analyzer.analyze_user_personality(
                    user_id, recent_messages, user.personality_traits
                )
                
                if updated_personality and updated_personality != user.personality_traits:
                    await db_client.update_user_personality(user_id, updated_personality)
                    personality_insights = {
                        "updated": True,
                        "traits": updated_personality.dict()
                    }
                    logger.info("User personality updated", user_id)
            
            # Determine if follow-up question is needed
            requires_follow_up, follow_up_question = await self._should_ask_follow_up(
                current_message, memory_context, emotional_state
            )
            
            # Create analysis result
            analysis_result = UserAnalysisResult(
                user_id=user_id,
                current_message=current_message,
                personality_insights=personality_insights,
                emotional_state=EmotionalState(emotional_state) if emotional_state in [e.value for e in EmotionalState] else EmotionalState.STABLE,
                context_from_memory=memory_context,
                requires_follow_up_question=requires_follow_up,
                follow_up_question=follow_up_question
            )
            
            logger.debug("User analysis completed successfully", user_id)
            
            # Update state
            return {
                "user_personality": user.personality_traits,
                "memory_context": memory_context,
                "analysis_result": analysis_result,
                "message_count": len(recent_messages)
            }
            
        except Exception as e:
            logger.error("Error in user analysis node", state["user_id"], e)
            # Return minimal analysis result on error
            return {
                "analysis_result": UserAnalysisResult(
                    user_id=state["user_id"],
                    current_message=state["current_message"],
                    personality_insights={},
                    emotional_state=EmotionalState.STABLE,
                    context_from_memory=[],
                    requires_follow_up_question=False
                )
            }
    
    async def _get_or_create_user(self, user_id: str) -> User:
        """Get existing user or create new one"""
        
        user = await db_client.get_user(user_id)
        
        if not user:
            # Create new user with basic info
            user = await db_client.create_user(
                user_id=user_id,
                first_name="کاربر",  # Default name
                username=None
            )
            logger.info("New user created", user_id)
        
        return user
    
    def _detect_emotional_state(self, message: str) -> EmotionalState:
        """Detect emotional state from message content"""
        
        message_lower = message.lower()
        
        # Check for emotion keywords
        for persian_word, emotion in self.emotion_keywords.items():
            if persian_word in message_lower:
                # Convert string to EmotionalState enum
                if emotion == 'happy':
                    return EmotionalState.EXCITED
                elif emotion == 'sad':
                    return EmotionalState.DEPRESSED
                elif emotion == 'angry':
                    return EmotionalState.STABLE  # No angry state in enum
                elif emotion == 'anxious':
                    return EmotionalState.ANXIOUS
                elif emotion == 'calm':
                    return EmotionalState.STABLE
                elif emotion == 'excited':
                    return EmotionalState.EXCITED
        
        # Check for emotional indicators
        if any(word in message_lower for word in ['؟', 'چرا', 'چگونه', 'چطور']):
            if any(word in message_lower for word in ['مشکل', 'درد', 'ناراحت']):
                return EmotionalState.CONFUSED
        
        # Check message length and punctuation for intensity
        if '!' in message:
            return EmotionalState.EXCITED
        elif message.count('؟') > 1:
            return EmotionalState.CONFUSED
        elif len(message) > 200:
            return EmotionalState.ANXIOUS
        
        return EmotionalState.STABLE
    
    async def _should_ask_follow_up(self, message: str, context: List[str], 
                                   emotional_state: str) -> tuple[bool, str]:
        """Determine if a follow-up question should be asked"""
        
        try:
            # Conditions for asking follow-up questions
            follow_up_triggers = [
                # Vague messages
                len(message.strip()) < 20,
                
                # Emotional indicators without details
                emotional_state in ['sad', 'anxious', 'angry'] and 'چون' not in message,
                
                # General statements
                any(phrase in message.lower() for phrase in [
                    'خوب نیستم', 'بد حال', 'مشکل دارم', 'ناراحتم', 'خسته‌ام'
                ]),
                
                # First interaction (no context)
                len(context) == 0 and len(message) < 50
            ]
            
            should_ask = any(follow_up_triggers)
            
            if not should_ask:
                return False, None
            
            # Generate appropriate follow-up question
            follow_up_question = await self._generate_follow_up_question(
                message, emotional_state, context
            )
            
            return True, follow_up_question
            
        except Exception as e:
            logger.error("Error determining follow-up question", error=e)
            return False, None
    
    async def _generate_follow_up_question(self, message: str, emotional_state: str, 
                                          context: List[str]) -> str:
        """Generate appropriate follow-up question"""
        
        # Simple rule-based follow-up questions
        if emotional_state == 'sad':
            questions = [
                "می‌تونید بیشتر برام تعریف کنید که چه اتفاقی افتاده؟",
                "چه چیزی باعث شده که این احساس رو داشته باشید؟",
                "این احساس از کی شروع شده؟"
            ]
        elif emotional_state == 'anxious':
            questions = [
                "چه چیزی باعث نگرانی شما شده؟",
                "این اضطراب چه موقع بیشتر می‌شه؟",
                "می‌تونید بیشتر توضیح بدید که چه فکری شما رو نگران می‌کنه؟"
            ]
        elif emotional_state == 'angry':
            questions = [
                "چه اتفاقی باعث عصبانیتتون شده؟",
                "این احساس چقدر وقته که دارید؟",
                "می‌خواید بیشتر در مورد علت عصبانیتتون صحبت کنید؟"
            ]
        elif len(message) < 20:
            questions = [
                "می‌تونید کمی بیشتر توضیح بدید؟",
                "چه چیز خاصی توی ذهنتونه که می‌خواید درموردش صحبت کنید؟",
                "امروز چطور بوده؟ چه خبر؟"
            ]
        else:
            questions = [
                "می‌تونید بیشتر توضیح بدید؟",
                "چه احساسی نسبت به این موضوع دارید؟",
                "این موضوع چقدر مدته که ذهنتونو درگیر کرده؟"
            ]
        
        # Select a random question to seem more natural
        import random
        return random.choice(questions)