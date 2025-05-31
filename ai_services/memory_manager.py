import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re

from database.mongodb import db_client  
from database.models import Memory, MemoryType, Message, ImportanceLevel
from utils.logger import logger

class MemoryManager:
    """Manages short-term and long-term memory for users"""
    
    def __init__(self):
        self.short_term_cache = {}  # In-memory cache for short-term memories
        self.importance_keywords = {
            'high': [
                'خودکشی', 'مرگ', 'درد', 'افسرده', 'ناامید', 'تنها', 'ترس', 'نگران', 'اضطراب',
                'عاشق', 'ازدواج', 'طلاق', 'خانواده', 'پدر', 'مادر', 'فرزند', 'کار', 'شغل',
                'بیماری', 'سلامت', 'دردسر', 'مشکل', 'بحران', 'تصمیم مهم'
            ],
            'medium': [
                'دوست', 'رابطه', 'احساس', 'خوشحال', 'ناراحت', 'عصبانی', 'آرام',
                'تغییر', 'برنامه', 'هدف', 'آینده', 'گذشته', 'خاطره', 'تجربه'
            ],
            'low': [
                'روز', 'هفته', 'ماه', 'وقت', 'زمان', 'عادی', 'معمولی', 'همیشه'
            ]
        }
    
    async def store_conversation_memory(self, user_id: str, message: Message, 
                                     context: Dict[str, Any] = None) -> bool:
        """Store conversation message in appropriate memory type"""
        
        try:
            # Determine importance level
            importance_score = self._calculate_importance_score(message, context)
            importance_level = self._score_to_importance_level(importance_score)
            
            # Always store in short-term memory first
            await self._store_short_term_memory(user_id, message, importance_score)
            
            # Store in long-term if important enough
            if importance_score >= 0.7:
                await self._store_long_term_memory(user_id, message, importance_score)
                logger.debug(f"Message stored in long-term memory (score: {importance_score:.2f})", user_id)
            
            # Update cache
            self._update_short_term_cache(user_id, message, importance_score)
            
            return True
            
        except Exception as e:
            logger.error("Failed to store conversation memory", user_id, e)
            return False
    
    async def get_relevant_context(self, user_id: str, current_message: str, 
                                 limit: int = 10) -> List[str]:
        """Get relevant context from memories for current conversation"""
        
        try:
            context_items = []
            
            # Get short-term memories (recent conversation)
            short_term_memories = await db_client.get_relevant_memories(
                user_id, MemoryType.SHORT_TERM, limit=limit//2
            )
            
            for memory in short_term_memories:
                context_items.append(f"Recent: {memory.content}")
                # Update access count
                await db_client.update_memory_access(memory.id)
            
            # Get relevant long-term memories
            long_term_memories = await self._get_contextually_relevant_memories(
                user_id, current_message, limit=limit//2
            )
            
            for memory in long_term_memories:
                context_items.append(f"Background: {memory.content}")
                await db_client.update_memory_access(memory.id)
            
            return context_items
            
        except Exception as e:
            logger.error("Failed to get relevant context", user_id, e)
            return []
    
    async def _get_contextually_relevant_memories(self, user_id: str, current_message: str,
                                                limit: int = 5) -> List[Memory]:
        """Get long-term memories that are contextually relevant to current message"""
        
        try:
            # Get all long-term memories
            all_memories = await db_client.get_relevant_memories(
                user_id, MemoryType.LONG_TERM, limit=50
            )
            
            if not all_memories:
                return []
            
            # Score memories based on relevance to current message
            scored_memories = []
            current_words = set(self._extract_keywords(current_message.lower()))
            
            for memory in all_memories:
                memory_words = set(self._extract_keywords(memory.content.lower()))
                
                # Calculate similarity (simple word overlap)
                overlap = len(current_words.intersection(memory_words))
                total_words = len(current_words.union(memory_words))
                
                if total_words > 0:
                    similarity = overlap / total_words
                    
                    # Boost score based on memory importance and recency
                    time_factor = self._calculate_time_relevance(memory.created_at)
                    access_factor = min(1.0, memory.access_count / 10)  # Frequently accessed memories
                    
                    final_score = (similarity * 0.5) + (memory.importance_score * 0.3) + (time_factor * 0.1) + (access_factor * 0.1)
                    
                    scored_memories.append((memory, final_score))
            
            # Sort by score and return top memories
            scored_memories.sort(key=lambda x: x[1], reverse=True)
            return [memory for memory, score in scored_memories[:limit] if score > 0.2]
            
        except Exception as e:
            logger.error("Failed to get contextually relevant memories", user_id, e)
            return []
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text"""
        
        # Remove common Persian stop words
        stop_words = {
            'و', 'در', 'به', 'از', 'که', 'این', 'با', 'برای', 'تا', 'بر', 'یا', 'اما',
            'چون', 'اگر', 'وقتی', 'البته', 'بعد', 'قبل', 'حالا', 'الان', 'امروز', 'دیروز',
            'است', 'هست', 'بود', 'شد', 'می', 'نمی', 'خیلی', 'زیاد', 'کم', 'فقط'
        }
        
        # Extract words (Persian and English)
        words = re.findall(r'[\u0600-\u06FF\u0700-\u077F\w]+', text)
        
        # Filter meaningful words
        keywords = []
        for word in words:
            if len(word) > 2 and word not in stop_words:
                keywords.append(word)
        
        return keywords
    
    def _calculate_importance_score(self, message: Message, context: Dict[str, Any] = None) -> float:
        """Calculate importance score for a message"""
        
        score = 0.5  # Base score
        content = message.content.lower()
        
        # Check for high importance keywords
        for keyword in self.importance_keywords['high']:
            if keyword in content:
                score += 0.15
        
        # Check for medium importance keywords  
        for keyword in self.importance_keywords['medium']:
            if keyword in content:
                score += 0.08
        
        # Emotional intensity bonus
        if message.emotion_detected:
            emotion_weights = {
                'sad': 0.2, 'angry': 0.15, 'anxious': 0.2, 'worried': 0.15,
                'excited': 0.1, 'happy': 0.05, 'frustrated': 0.15
            }
            score += emotion_weights.get(message.emotion_detected, 0.05)
        
        # Length bonus (longer messages often more important)
        if len(content) > 100:
            score += 0.1
        elif len(content) > 200:
            score += 0.15
        
        # Question detection (questions often important)
        if '?' in content or 'چرا' in content or 'چگونه' in content or 'کی' in content:
            score += 0.1
        
        # Personal pronouns (personal stories more important)
        personal_pronouns = ['من', 'خودم', 'خود', 'مال من', 'برای من']
        for pronoun in personal_pronouns:
            if pronoun in content:
                score += 0.05
        
        # Clamp score between 0 and 1
        return max(0.0, min(1.0, score))
    
    def _score_to_importance_level(self, score: float) -> ImportanceLevel:
        """Convert numeric score to importance level"""
        if score >= 0.7:
            return ImportanceLevel.HIGH
        elif score >= 0.4:
            return ImportanceLevel.MEDIUM
        else:
            return ImportanceLevel.LOW
    
    def _calculate_time_relevance(self, created_at: datetime) -> float:
        """Calculate time-based relevance (more recent = more relevant)"""
        days_ago = (datetime.now() - created_at).days
        
        if days_ago <= 1:
            return 1.0
        elif days_ago <= 7:
            return 0.8
        elif days_ago <= 30:
            return 0.6
        elif days_ago <= 90:
            return 0.4
        else:
            return 0.2
    
    async def _store_short_term_memory(self, user_id: str, message: Message, importance_score: float):
        """Store message in short-term memory"""
        
        content = f"{message.role.value}: {message.content}"
        if message.emotion_detected:
            content += f" [emotion: {message.emotion_detected}]"
        
        await db_client.store_memory(
            user_id=user_id,
            content=content,
            memory_type=MemoryType.SHORT_TERM,
            importance_score=importance_score
        )
    
    async def _store_long_term_memory(self, user_id: str, message: Message, importance_score: float):
        """Store important message in long-term memory"""
        
        # Create a more processed version for long-term storage
        content = self._create_long_term_summary(message)
        
        await db_client.store_memory(
            user_id=user_id,
            content=content,
            memory_type=MemoryType.LONG_TERM,
            importance_score=importance_score
        )
    
    def _create_long_term_summary(self, message: Message) -> str:
        """Create a summary suitable for long-term storage"""
        
        summary_parts = []
        
        # Add timestamp context
        time_context = message.timestamp.strftime("%Y-%m-%d")
        summary_parts.append(f"[{time_context}]")
        
        # Add emotional context
        if message.emotion_detected:
            summary_parts.append(f"User felt {message.emotion_detected}")
        
        # Add content (possibly truncated)
        content = message.content
        if len(content) > 200:
            content = content[:200] + "..."
        
        summary_parts.append(f"Said: {content}")
        
        return " - ".join(summary_parts)
    
    def _update_short_term_cache(self, user_id: str, message: Message, importance_score: float):
        """Update in-memory cache for quick access"""
        
        if user_id not in self.short_term_cache:
            self.short_term_cache[user_id] = []
        
        cache_entry = {
            'content': message.content,
            'role': message.role.value,
            'timestamp': message.timestamp,
            'importance': importance_score,
            'emotion': message.emotion_detected
        }
        
        self.short_term_cache[user_id].append(cache_entry)
        
        # Keep only recent entries in cache
        if len(self.short_term_cache[user_id]) > 20:
            self.short_term_cache[user_id] = self.short_term_cache[user_id][-20:]
    
    async def cleanup_old_memories(self, user_id: str = None):
        """Clean up old short-term memories and optimize storage"""
        
        try:
            if user_id:
                # Clean up for specific user
                deleted_count = await db_client.cleanup_old_short_term_memories(user_id, days=7)
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old memories for user {user_id}")
            else:
                # This would need to be implemented to clean up all users
                logger.info("Global memory cleanup not implemented yet")
            
            # Clean up cache
            self._cleanup_cache()
            
        except Exception as e:
            logger.error("Failed to cleanup old memories", user_id, e)
    
    def _cleanup_cache(self):
        """Clean up old cache entries"""
        current_time = datetime.now()
        
        for user_id in list(self.short_term_cache.keys()):
            if user_id in self.short_term_cache:
                # Remove entries older than 1 hour
                self.short_term_cache[user_id] = [
                    entry for entry in self.short_term_cache[user_id]
                    if (current_time - entry['timestamp']).seconds < 3600
                ]
                
                # Remove empty user caches
                if not self.short_term_cache[user_id]:
                    del self.short_term_cache[user_id]
    
    async def get_memory_summary(self, user_id: str) -> Dict[str, Any]:
        """Get summary of user's memory usage"""
        
        try:
            short_term_memories = await db_client.get_relevant_memories(
                user_id, MemoryType.SHORT_TERM, limit=100
            )
            long_term_memories = await db_client.get_relevant_memories(
                user_id, MemoryType.LONG_TERM, limit=100
            )
            
            return {
                'short_term_count': len(short_term_memories),
                'long_term_count': len(long_term_memories),
                'total_memories': len(short_term_memories) + len(long_term_memories),
                'cache_entries': len(self.short_term_cache.get(user_id, [])),
                'most_recent_memory': short_term_memories[0].created_at if short_term_memories else None
            }
            
        except Exception as e:
            logger.error("Failed to get memory summary", user_id, e)
            return {'error': str(e)}

# Global memory manager instance
memory_manager = MemoryManager()