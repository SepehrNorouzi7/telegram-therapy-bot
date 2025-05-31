import asyncio
from openai import OpenAI
from openai.types.chat import ChatCompletion
from typing import List, Dict, Any, Optional
import json
import time
from concurrent.futures import ThreadPoolExecutor

from config import Config
from utils.logger import logger

class OpenRouterClient:
    """OpenRouter AI client for therapy bot"""
    
    def __init__(self):
        self.client = OpenAI(
            base_url=Config.OPENROUTER_BASE_URL,
            api_key=Config.OPENROUTER_API_KEY,
        )
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.request_count = 0
        self.last_request_time = 0
        
    async def _run_in_executor(self, func, *args):
        """Run AI request in thread pool to avoid blocking"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args)
    
    def _rate_limit(self):
        """Simple rate limiting to avoid overwhelming the API"""
        current_time = time.time()
        if current_time - self.last_request_time < 1:  # At least 1 second between requests
            time.sleep(1)
        self.last_request_time = time.time()
    
    def _build_therapy_system_prompt(self, personality_traits: Dict[str, Any] = None, 
                                   user_context: str = None) -> str:
        """Build system prompt for therapy conversations"""
        
        base_prompt = """You are an empathetic and professional AI therapist assistant. Your role is to provide supportive, non-judgmental therapeutic conversation in Persian/Farsi.

                        Key guidelines:
                        - Respond naturally and conversationally, like a human therapist would
                        - Ask follow-up questions when appropriate to understand the user better  
                        - Use active listening techniques and validate emotions
                        - Provide gentle guidance and coping strategies when suitable
                        - Be warm, empathetic, and supportive
                        - Sometimes ask clarifying questions before responding
                        - Don't rush to give advice - sometimes just listening is enough
                        - Use appropriate Persian/Farsi expressions and cultural context
                        - Keep responses conversational, not overly formal or clinical
                        - Write ONLY the actual response text - no stage directions, no text in parentheses like (با لحنی آرام), no emotional descriptions
                        - Do not include any meta-text, action descriptions, or narrative elements
                        - Just provide direct, natural therapeutic response

                        IMPORTANT: You are having a real-time conversation. Sometimes you should:
                        - Ask a question to better understand the situation
                        - Request clarification about feelings or events
                        - Show curiosity about the user's perspective
                        - Respond with empathy before giving any advice

                        CRITICAL: Write only the words you would actually say - no stage directions or descriptions in parentheses."""

        # Add personality context if available
        if personality_traits:
            personality_context = f"""
User Personality Context:
- Communication Style: {personality_traits.get('communication_style', 'supportive')}
- Emotional State: {personality_traits.get('emotional_state', 'stable')}
- Preferred Therapy Approach: {personality_traits.get('preferred_therapy_approach', 'humanistic')}
- Openness: {personality_traits.get('openness', 0.5)}/1.0
- Extraversion: {personality_traits.get('extraversion', 0.5)}/1.0
- Neuroticism: {personality_traits.get('neuroticism', 0.5)}/1.0

Adapt your communication style to match their preferences."""
            base_prompt += personality_context
        
        # Add user context from memory
        if user_context:
            context_addition = f"""
Previous Context:
{user_context}

Consider this context when responding, but don't explicitly reference it unless relevant."""
            base_prompt += context_addition
        
        return base_prompt
    
    def _create_chat_messages(self, system_prompt: str, user_message: str, 
                            conversation_history: List[Dict[str, str]] = None) -> List[Dict[str, str]]:
        """Create messages array for chat completion"""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add recent conversation history if available
        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 10 messages for context
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        return messages
    
    async def generate_therapy_response(self, user_message: str, user_id: str = None,
                                    personality_traits: Dict[str, Any] = None,
                                    user_context: str = None,
                                    conversation_history: List[Dict[str, str]] = None,
                                    context: Dict[str, Any] = None,
                                    emotional_state: str = None) -> Dict[str, Any]:
        """Generate therapy response using OpenRouter"""
        
        def _make_request():
            try:
                self._rate_limit()
                
                # Build system prompt
                system_prompt = self._build_therapy_system_prompt(personality_traits, user_context)
                
                # Create messages
                messages = self._create_chat_messages(system_prompt, user_message, conversation_history)
                
                # Make API request
                start_time = time.time()
                completion = self.client.chat.completions.create(
                    timeout=60,
                    extra_headers={
                        "HTTP-Referer": Config.SITE_URL,
                        "X-Title": Config.SITE_NAME,
                    },
                    model=Config.AI_MODEL,
                    messages=messages,
                    temperature=0.8,  # Slightly creative but not too random
                    max_tokens=1500,   # Reasonable length for therapy responses
                    top_p=0.9,
                    frequency_penalty=0.1,
                    presence_penalty=0.1
                )
                
                response_time = time.time() - start_time
                
                # Extract response
                response_text = completion.choices[0].message.content.strip()
                
                # Calculate tokens used (approximate if not provided)
                tokens_used = getattr(completion, 'usage', None)
                if tokens_used:
                    total_tokens = tokens_used.total_tokens
                else:
                    total_tokens = len(' '.join([msg['content'] for msg in messages]).split()) * 1.3
                
                # Log successful request
                logger.log_ai_request(user_id, Config.AI_MODEL, int(total_tokens))
                logger.info(f"AI response generated in {response_time:.2f}s", user_id)
                
                return {
                    "success": True,
                    "response": response_text,
                    "tokens_used": int(total_tokens),
                    "response_time": response_time,
                    "model_used": Config.AI_MODEL
                }
                
            except Exception as e:
                logger.error(f"OpenRouter API error", user_id, e)
                return {
                    "success": False,
                    "error": str(e),
                    "response": None
                }
        
        return await self._run_in_executor(_make_request)
    
    async def analyze_personality_traits(self, conversation_text: str, 
                                       current_traits: Dict[str, Any] = None,
                                       user_id: str = None) -> Dict[str, Any]:
        """Analyze personality traits from conversation"""
        
        def _analyze():
            try:
                self._rate_limit()
                
                system_prompt = """You are a personality analysis expert. Analyze the given conversation text and provide personality insights in JSON format.

Return ONLY a valid JSON object with these fields:
{
  "openness": 0.0-1.0,
  "conscientiousness": 0.0-1.0, 
  "extraversion": 0.0-1.0,
  "agreeableness": 0.0-1.0,
  "neuroticism": 0.0-1.0,
  "communication_style": "direct/supportive/analytical/empathetic",
  "emotional_state": "stable/anxious/depressed/excited/confused",
  "confidence_level": 0.0-1.0
}

Base your analysis on communication patterns, word choice, emotional expression, and content themes."""

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze this conversation text:\n\n{conversation_text}"}
                ]
                
                completion = self.client.chat.completions.create(
                    extra_headers={
                        "HTTP-Referer": Config.SITE_URL,
                        "X-Title": Config.SITE_NAME,
                    },
                    model=Config.AI_MODEL,
                    messages=messages,
                    temperature=0.3,  # Lower temperature for more consistent analysis
                    max_tokens=800
                )
                
                response_text = completion.choices[0].message.content.strip()
                
                # Try to parse JSON response
                try:
                    personality_data = json.loads(response_text)
                    logger.info("Personality analysis completed", user_id)
                    return {
                        "success": True,
                        "traits": personality_data
                    }
                except json.JSONDecodeError:
                    logger.warning("Failed to parse personality analysis JSON", user_id)
                    return {
                        "success": False,
                        "error": "Invalid JSON response from AI"
                    }
                    
            except Exception as e:
                logger.error("Personality analysis error", user_id, e)
                return {
                    "success": False,
                    "error": str(e)
                }
        
        return await self._run_in_executor(_analyze)
    
    async def detect_emotion(self, text: str, user_id: str = None) -> str:
        """Detect emotion from text"""
        
        def _detect():
            try:
                self._rate_limit()
                
                system_prompt = """Detect the primary emotion in the given text. 
Respond with ONLY ONE WORD from these options: happy, sad, angry, anxious, excited, confused, neutral, frustrated, hopeful, worried"""
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ]
                
                completion = self.client.chat.completions.create(
                    extra_headers={
                        "HTTP-Referer": Config.SITE_URL,
                        "X-Title": Config.SITE_NAME,
                    },
                    model=Config.AI_MODEL,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=10
                )
                
                emotion = completion.choices[0].message.content.strip().lower()
                return emotion
                
            except Exception as e:
                logger.error("Emotion detection error", user_id, e)
                return "neutral"
        
        return await self._run_in_executor(_detect)
    
    async def generate_follow_up_question(self, conversation_context: str, 
                                        user_id: str = None) -> Optional[str]:
        """Generate a follow-up question based on conversation context"""
        
        def _generate():
            try:
                self._rate_limit()
                
                system_prompt = """You are a therapist. Based on the conversation context, generate a thoughtful follow-up question in Persian/Farsi that would help understand the user better.

Rules:
- Ask only ONE question
- Make it empathetic and non-intrusive
- Focus on feelings, thoughts, or experiences
- Keep it conversational, not clinical
- If no good follow-up is needed, respond with "NONE"

Examples of good follow-up questions:
- "چه احساسی در آن لحظه داشتید؟"
- "این موضوع چقدر برایتان مهم است؟"
- "آیا این اتفاق قبلاً هم برایتان پیش آمده؟"
"""

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Conversation context:\n{conversation_context}"}
                ]
                
                completion = self.client.chat.completions.create(
                    extra_headers={
                        "HTTP-Referer": Config.SITE_URL,
                        "X-Title": Config.SITE_NAME,
                    },
                    model=Config.AI_MODEL,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=200
                )
                
                question = completion.choices[0].message.content.strip()
                
                if question.upper() == "NONE" or len(question) < 5:
                    return None
                
                return question
                
            except Exception as e:
                logger.error("Follow-up question generation error", user_id, e)
                return None
        
        return await self._run_in_executor(_generate)
    
    def close(self):
        """Close the client and cleanup resources"""
        self.executor.shutdown(wait=True)
        logger.info("OpenRouter client closed")

# Global client instance
openrouter_client = OpenRouterClient()