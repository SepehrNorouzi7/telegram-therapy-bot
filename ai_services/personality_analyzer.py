import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json

from ai_services.openrouter_client import openrouter_client
from database.mongodb import db_client
from database.models import PersonalityTraits, Message, MemoryType
from utils.logger import logger

class PersonalityAnalyzer:
    """Analyzes and updates user personality traits"""
    
    def __init__(self):
        self.analysis_cache = {}  # Cache recent analyses
        self.message_buffers = {}  # Buffer messages for batch analysis
        
    async def analyze_user_personality(self, user_id: str, recent_messages: List[Message],
                                     current_traits: PersonalityTraits = None) -> Optional[PersonalityTraits]:
        """Analyze user personality from recent messages"""
        
        try:
            # Prepare conversation text for analysis
            conversation_text = self._prepare_conversation_text(recent_messages)
            
            if len(conversation_text) < 50:  # Not enough data
                logger.debug("Insufficient conversation data for personality analysis", user_id)
                return current_traits
            
            # Check if we have recent analysis in cache
            cache_key = f"{user_id}_{hash(conversation_text[:200])}"
            if cache_key in self.analysis_cache:
                cached_result = self.analysis_cache[cache_key]
                if (datetime.now() - cached_result['timestamp']).seconds < 300:  # 5 minutes cache
                    logger.debug("Using cached personality analysis", user_id)
                    return cached_result['traits']
            
            # Perform AI analysis
            analysis_result = await openrouter_client.analyze_personality_traits(
                conversation_text, 
                current_traits.dict() if current_traits else None,
                user_id
            )
            
            if not analysis_result['success']:
                logger.warning("Personality analysis failed", user_id)
                return current_traits
            
            # Create updated personality traits
            updated_traits = self._merge_personality_traits(
                current_traits, 
                analysis_result['traits']
            )
            
            # Cache the result
            self.analysis_cache[cache_key] = {
                'traits': updated_traits,
                'timestamp': datetime.now()
            }
            
            # Store insights in long-term memory
            await self._store_personality_insights(user_id, analysis_result['traits'])
            
            logger.info("Personality analysis completed", user_id)
            return updated_traits
            
        except Exception as e:
            logger.error("Error in personality analysis", user_id, e)
            return current_traits
    
    def _prepare_conversation_text(self, messages: List[Message]) -> str:
        """Prepare conversation text for analysis"""
        
        # Focus on user messages for personality analysis
        user_messages = [msg for msg in messages if msg.role.value == "user"]
        
        if not user_messages:
            return ""
        
        # Take recent messages (last 2 weeks of conversation)
        recent_messages = user_messages[-20:]  # Last 20 user messages
        
        conversation_parts = []
        for msg in recent_messages:
            # Add emotional context if available
            emotion_context = f" [احساس: {msg.emotion_detected}]" if msg.emotion_detected else ""
            conversation_parts.append(f"{msg.content}{emotion_context}")
        
        return "\n".join(conversation_parts)
    
    def _merge_personality_traits(self, current: PersonalityTraits, new_analysis: Dict[str, Any]) -> PersonalityTraits:
        """Merge current traits with new analysis using weighted average"""
        
        if not current:
            # First analysis - use AI results directly
            return PersonalityTraits(**{
                'openness': new_analysis.get('openness', 0.5),
                'conscientiousness': new_analysis.get('conscientiousness', 0.5),
                'extraversion': new_analysis.get('extraversion', 0.5),
                'agreeableness': new_analysis.get('agreeableness', 0.5),
                'neuroticism': new_analysis.get('neuroticism', 0.5),
                'communication_style': new_analysis.get('communication_style', 'supportive'),
                'emotional_state': new_analysis.get('emotional_state', 'stable'),
                'preferred_therapy_approach': current.preferred_therapy_approach if current else 'humanistic'
            })
        
        # Weighted merge - 70% current, 30% new (gradual adaptation)
        weight_current = 0.7
        weight_new = 0.3
        
        # Confidence factor - if AI is more confident, give it more weight
        confidence = new_analysis.get('confidence_level', 0.5)
        if confidence > 0.8:
            weight_current = 0.6
            weight_new = 0.4
        elif confidence < 0.3:
            weight_current = 0.8
            weight_new = 0.2
        
        merged_traits = PersonalityTraits(
            openness=self._weighted_average(
                current.openness, 
                new_analysis.get('openness', current.openness), 
                weight_current, weight_new
            ),
            conscientiousness=self._weighted_average(
                current.conscientiousness,
                new_analysis.get('conscientiousness', current.conscientiousness),
                weight_current, weight_new
            ),
            extraversion=self._weighted_average(
                current.extraversion,
                new_analysis.get('extraversion', current.extraversion),
                weight_current, weight_new
            ),
            agreeableness=self._weighted_average(
                current.agreeableness,
                new_analysis.get('agreeableness', current.agreeableness),
                weight_current, weight_new
            ),
            neuroticism=self._weighted_average(
                current.neuroticism,
                new_analysis.get('neuroticism', current.neuroticism),
                weight_current, weight_new
            ),
            communication_style=new_analysis.get('communication_style', current.communication_style),
            emotional_state=new_analysis.get('emotional_state', current.emotional_state),
            preferred_therapy_approach=current.preferred_therapy_approach  # Keep user's preference
        )
        
        return merged_traits
    
    def _weighted_average(self, current: float, new: float, weight_current: float, weight_new: float) -> float:
        """Calculate weighted average and ensure it's within bounds"""
        result = (current * weight_current) + (new * weight_new)
        return max(0.0, min(1.0, result))  # Clamp between 0 and 1
    
    async def _store_personality_insights(self, user_id: str, traits: Dict[str, Any]):
        """Store personality insights in long-term memory"""
        
        try:
            # Create insight summary
            insights = []
            
            # Analyze significant traits
            for trait, value in traits.items():
                if trait in ['openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism']:
                    if value > 0.7:
                        insights.append(f"High {trait}: {value:.2f}")
                    elif value < 0.3:
                        insights.append(f"Low {trait}: {value:.2f}")
            
            # Add communication and emotional info
            if 'communication_style' in traits:
                insights.append(f"Communication: {traits['communication_style']}")
            if 'emotional_state' in traits:
                insights.append(f"Emotional state: {traits['emotional_state']}")
            
            if insights:
                insight_text = "Personality insights: " + ", ".join(insights)
                
                # Store in long-term memory with high importance
                await db_client.store_memory(
                    user_id=user_id,
                    content=insight_text,
                    memory_type=MemoryType.LONG_TERM,
                    importance_score=0.8
                )
                
                logger.debug("Personality insights stored in memory", user_id)
        
        except Exception as e:
            logger.error("Failed to store personality insights", user_id, e)
    
    async def should_update_personality(self, user_id: str, message_count: int) -> bool:
        """Determine if personality should be updated based on message count and patterns"""
        
        # Update every 10 messages for new users, every 20 for established users
        if message_count < 50:
            return message_count % 10 == 0
        else:
            return message_count % 20 == 0
    
    async def get_personality_summary(self, traits: PersonalityTraits) -> str:
        """Generate a human-readable personality summary"""
        
        summary_parts = []
        
        # Big Five analysis
        if traits.openness > 0.7:
            summary_parts.append("creative and open to new experiences")
        elif traits.openness < 0.3:
            summary_parts.append("prefers familiar and traditional approaches")
        
        if traits.extraversion > 0.7:
            summary_parts.append("outgoing and energetic")
        elif traits.extraversion < 0.3:
            summary_parts.append("introverted and reflective")
        
        if traits.neuroticism > 0.7:
            summary_parts.append("sensitive to stress and emotions")
        elif traits.neuroticism < 0.3:
            summary_parts.append("emotionally stable and calm")
        
        # Communication style
        style_descriptions = {
            'direct': 'straightforward communication',
            'supportive': 'supportive and empathetic communication',
            'analytical': 'logical and detail-oriented communication',
            'empathetic': 'emotionally attuned communication'
        }
        
        if traits.communication_style in style_descriptions:
            summary_parts.append(style_descriptions[traits.communication_style])
        
        # Emotional state
        if traits.emotional_state != 'stable':
            summary_parts.append(f"currently feeling {traits.emotional_state}")
        
        if summary_parts:
            return "User shows: " + ", ".join(summary_parts)
        else:
            return "User personality profile is being developed"
    
    def cleanup_cache(self):
        """Clean up old cache entries"""
        current_time = datetime.now()
        expired_keys = []
        
        for key, value in self.analysis_cache.items():
            if (current_time - value['timestamp']).seconds > 1800:  # 30 minutes
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.analysis_cache[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired personality cache entries")

# Global personality analyzer instance
personality_analyzer = PersonalityAnalyzer()