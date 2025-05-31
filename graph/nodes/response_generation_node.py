import asyncio
import random
from typing import Dict, Any, List
from datetime import datetime

from ai_services.openrouter_client import openrouter_client
from ai_services.memory_manager import memory_manager
from database.models import TherapyResponse, Message, MessageRole, ImportanceLevel
from graph.state import TherapyState
from config import Config
from utils.logger import logger

class ResponseGenerationNode:
    """Node 2: Generates therapeutic responses"""
    
    def __init__(self):
        self.response_templates = {
            'empathetic': [
                "متوجه می‌شم که {emotion} هستید.",
                "به نظر می‌رسه که {situation} براتون سخت بوده.",
                "احساساتتون کاملاً طبیعی و قابل درک است."
            ],
            'supportive': [
                "خیلی شجاع هستید که این موضوع رو با من در میان گذاشتید.",
                "گام به گام می‌تونیم این مسئله رو حل کنیم.",
                "شما تنها نیستید، من اینجا هستم تا کمکتون کنم."
            ],
            'questioning': [
                "چه احساسی نسبت به این موضوع دارید؟",
                "این وضعیت چه تأثیری روی زندگی روزانه‌تون داره؟",
                "آیا قبلاً چنین تجربه‌ای داشته‌اید؟"
            ]
        }
        
        # Delay ranges for natural response timing
        self.response_delays = {
            'quick': (1.0, 2.0),      # Simple acknowledgments
            'normal': (2.0, 4.0),     # Regular responses
            'thoughtful': (3.0, 6.0)  # Complex analysis responses
        }
    
    async def execute(self, state: TherapyState) -> Dict[str, Any]:
        """Execute response generation"""
        
        try:
            user_id = state["user_id"]  # Changed from state.user_id
            analysis_result = state["analysis_result"]  # Changed from state.analysis_result
            
            if not analysis_result:
                logger.error("No analysis result available for response generation", user_id)
                return {"therapy_response": self._create_error_response()}
            
            logger.debug("Starting response generation", user_id)
            
            # Determine response delay type
            delay_type = self._determine_delay_type(analysis_result)
            
            # Add natural delay before responding
            await self._add_response_delay(delay_type)
            
            # Generate response based on analysis
            if analysis_result.requires_follow_up_question:
                # Generate follow-up question response
                response = await self._generate_follow_up_response(
                    state, analysis_result
                )
            else:
                # Generate therapeutic response
                response = await self._generate_therapeutic_response(
                    state, analysis_result
                )
            
            # Store conversation in memory
            await self._store_conversation_memory(state, response)
            
            logger.debug("Response generation completed", user_id)
            
            return {"therapy_response": response}
            
        except Exception as e:
            logger.error("Error in response generation node", state["user_id"], e)
            return {"therapy_response": self._create_error_response()}
    
    def _determine_delay_type(self, analysis_result) -> str:
        """Determine appropriate response delay type"""
        
        # Quick responses for simple acknowledgments
        if len(analysis_result.current_message) < 30:
            return 'quick'
        
        # Thoughtful responses for emotional or complex messages
        if (analysis_result.emotional_state in ['sad', 'anxious', 'angry'] or 
            len(analysis_result.current_message) > 150 or
            analysis_result.requires_follow_up_question):
            return 'thoughtful'
        
        return 'normal'
    
    async def _add_response_delay(self, delay_type: str):
        """Add natural delay before responding"""
        
        min_delay, max_delay = self.response_delays[delay_type]
        delay = random.uniform(min_delay, max_delay)
        
        logger.debug(f"Adding {delay:.1f}s response delay ({delay_type})")
        await asyncio.sleep(delay)
    
    async def _generate_follow_up_response(self, state: TherapyState, 
                                         analysis_result) -> TherapyResponse:
        """Generate response with follow-up question"""
        
        # Create empathetic acknowledgment + follow-up question
        acknowledgment_templates = [
            "گوش می‌دم...",
            "می‌فهمم...",
            "متوجه هستم...",
            "درک می‌کنم..."
        ]
        
        acknowledgment = random.choice(acknowledgment_templates)
        
        response_text = f"{acknowledgment} {analysis_result.follow_up_question}"
        
        return TherapyResponse(
            response_text=response_text,
            requires_follow_up=True,
            follow_up_question=analysis_result.follow_up_question,
            emotion_detected=analysis_result.emotional_state,
            memory_importance=ImportanceLevel.MEDIUM
        )
    
    async def _generate_therapeutic_response(self, state: TherapyState,
                                           analysis_result) -> TherapyResponse:
        """Generate full therapeutic response using AI"""
        
        try:
            # Prepare context for AI
            context = self._prepare_ai_context(state, analysis_result)
            
            # Generate response using OpenRouter
            ai_response = await openrouter_client.generate_therapy_response(
                user_message=analysis_result.current_message,
                user_context=context.get('memory_context', ''),
                personality_traits=state["user_personality"].dict() if state["user_personality"] else None,
                emotional_state=analysis_result.emotional_state,
                user_id=state["user_id"],
                conversation_history=context.get('conversation_history', [])
            )
            
            if ai_response['success']:
                response_text = ai_response['response']
                
                # Determine if this response requires follow-up
                requires_follow_up = self._analyze_response_for_follow_up(response_text)
                
                return TherapyResponse(
                    response_text=response_text,
                    requires_follow_up=requires_follow_up,
                    emotion_detected=analysis_result.emotional_state,
                    personality_updates=analysis_result.personality_insights.get('traits'),
                    memory_importance=self._determine_memory_importance(analysis_result)
                )
            else:
                logger.warning("AI response generation failed, using fallback", state["user_id"])
                return self._generate_fallback_response(analysis_result)
                
        except Exception as e:
            logger.error("Error in AI response generation", state["user_id"], e)
            return self._generate_fallback_response(analysis_result)
    
    def _prepare_ai_context(self, state: TherapyState, analysis_result) -> Dict[str, Any]:
        """Prepare context for AI response generation"""
        
        return {
            'conversation_history': state["conversation_history"][-10:],  # Last 10 exchanges
            'memory_context': analysis_result.context_from_memory,
            'user_personality': state["user_personality"].dict() if state["user_personality"] else None,
            'emotional_state': analysis_result.emotional_state,
            'session_info': {
                'message_count': state["message_count"],
                'user_id': state["user_id"]  # For logging only
            }
        }
    
    def _analyze_response_for_follow_up(self, response_text: str) -> bool:
        """Analyze if response naturally leads to follow-up"""
        
        # Check for question marks
        if '؟' in response_text:
            return True
        
        # Check for phrases that invite response
        follow_up_phrases = [
            'چطور', 'چگونه', 'چه فکری', 'نظرتون چیه', 'می‌تونید بگید',
            'تجربه‌تون چی بوده', 'چه احساسی', 'به نظرتون'
        ]
        
        return any(phrase in response_text for phrase in follow_up_phrases)
    
    def _determine_memory_importance(self, analysis_result) -> ImportanceLevel:
        """Determine importance level for memory storage"""
        
        # High importance for emotional states or personality insights
        if (analysis_result.emotional_state in ['sad', 'anxious', 'angry'] or
            analysis_result.personality_insights.get('updated', False)):
            return ImportanceLevel.HIGH
        
        # Medium importance for follow-up questions
        if analysis_result.requires_follow_up_question:
            return ImportanceLevel.MEDIUM
        
        return ImportanceLevel.LOW
    
    def _generate_fallback_response(self, analysis_result) -> TherapyResponse:
        """Generate fallback response when AI fails"""
        
        emotional_state = analysis_result.emotional_state
        
        # Fallback responses based on emotional state
        fallback_responses = {
            'sad': "متوجه می‌شم که حالتون خوب نیست. می‌تونید بیشتر برام تعریف کنید؟",
            'anxious': "احساس می‌کنم که نگران هستید. چه چیزی باعث این احساس شده؟",
            'angry': "می‌بینم که عصبانی هستید. می‌خواید در موردش صحبت کنید؟",
            'excited': "انگار خیلی هیجان‌زده هستید! چه خبر خوبی شده؟",
            'confused': "به نظر مشغله ذهنی دارید. بیشتر توضیح می‌دید؟"
        }
        
        response_text = fallback_responses.get(
            emotional_state, 
            "گوش می‌دم... ادامه بدید."
        )
        
        return TherapyResponse(
            response_text=response_text,
            requires_follow_up=True,
            emotion_detected=emotional_state,
            memory_importance=ImportanceLevel.MEDIUM
        )
    
    def _create_error_response(self) -> TherapyResponse:
        """Create error response"""
        
        error_responses = [
            "متأسفم، مشکلی پیش آمده. می‌تونید دوباره تلاش کنید؟",
            "ببخشید، نتونستم پیامتون رو درست پردازش کنم. لطفاً دوباره بگید.",
            "مشکل فنی‌ای پیش اومده. چند لحظه صبر کنید و دوباره امتحان کنید."
        ]
        
        return TherapyResponse(
            response_text=random.choice(error_responses),
            requires_follow_up=False,
            memory_importance=ImportanceLevel.LOW
        )
    
    async def _store_conversation_memory(self, state: TherapyState, response: TherapyResponse):
        """Store conversation in memory"""
        
        try:
            # Store user message
            user_message = Message(
                role=MessageRole.USER,
                content=state["current_message"],
                emotion_detected=response.emotion_detected,
                context_importance=response.memory_importance
            )
            
            await memory_manager.store_conversation_memory(
                state["user_id"], user_message
            )
            
            # Store assistant response
            assistant_message = Message(
                role=MessageRole.ASSISTANT,
                content=response.response_text,
                context_importance=response.memory_importance
            )
            
            await memory_manager.store_conversation_memory(
                state["user_id"], assistant_message
            )
            
            logger.debug("Conversation stored in memory", state["user_id"])
            
        except Exception as e:
            logger.error("Failed to store conversation in memory", state["user_id"], e)