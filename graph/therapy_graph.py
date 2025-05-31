from typing import Dict, Any, List
from datetime import datetime
from langgraph.graph import StateGraph, END
from graph.state import TherapyState
from graph.nodes.user_analysis_node import UserAnalysisNode
from graph.nodes.response_generation_node import ResponseGenerationNode
from utils.logger import logger
from database.mongodb import db_client 

class TherapyGraph:
    """Main therapy conversation graph using LangGraph"""
    
    def __init__(self):
        self.user_analysis_node = UserAnalysisNode()
        self.response_generation_node = ResponseGenerationNode()
        self.graph = self._build_graph()
        
    def _build_graph(self):
        """Build the therapy conversation graph"""
        
        # Create the state graph
        workflow = StateGraph(TherapyState)
        
        # Add nodes
        workflow.add_node("user_analysis", self._user_analysis_wrapper)
        workflow.add_node("response_generation", self._response_generation_wrapper)
        
        # Add edges
        workflow.add_edge("user_analysis", "response_generation")
        workflow.add_edge("response_generation", END)
        
        # Set entry point
        workflow.set_entry_point("user_analysis")
        
        # Compile the graph
        return workflow.compile()
    
    async def _user_analysis_wrapper(self, state: TherapyState) -> Dict[str, Any]:
        """Wrapper for user analysis node"""
        try:
            result = await self.user_analysis_node.execute(state)
            logger.debug(f"User analysis completed for user {state['user_id']}")
            return result
        except Exception as e:
            logger.error(f"Error in user analysis node for user {state.get('user_id', 'unknown')}: {e}")
            from database.models import UserAnalysisResult
            return {
                "analysis_result": UserAnalysisResult(
                    user_id=state.get("user_id", ""),
                    current_message=state.get("current_message", ""),
                    personality_insights={},
                    emotional_state="stable",
                    context_from_memory=[],
                    requires_follow_up_question=False
                )
            }
    
    async def _response_generation_wrapper(self, state: TherapyState) -> Dict[str, Any]:
        """Wrapper for response generation node"""
        try:
            result = await self.response_generation_node.execute(state)
            logger.debug(f"Response generation completed for user {state.get('user_id')}")
            return result
        except Exception as e:
            logger.error(f"Error in response generation node for user {state.get('user_id', 'unknown')}: {e}")
            from database.models import TherapyResponse
            return {
                "therapy_response": TherapyResponse(
                    response_text="متأسفم، مشکلی پیش آمده. لطفاً دوباره تلاش کنید.",
                    requires_follow_up=False,
                    emotion_detected=None,
                    personality_updates=None
                )
            }
    
    async def process_message(self, user_id: str, message: str, conversation_id: str) -> Dict[str, Any]:
        """Process a user message through the therapy graph"""
        
        try:
            # Create initial state
            initial_state = TherapyState(
                user_id=user_id,
                current_message=message,
                conversation_history=[],
                user_personality=None,
                memory_context=[],
                analysis_result=None,
                therapy_response=None,
                processed_at=datetime.now(),
                message_count=0
            )
            
            logger.info(f"Processing message through therapy graph for user {user_id}")
            
            # Run the graph
            result = await self.graph.ainvoke(initial_state)
            
            # Extract the final response
            therapy_response = result.get("therapy_response")
            if not therapy_response:
                logger.error(f"No therapy response generated for user {user_id}")
                return {
                    "success": False,
                    "response": "متأسفم، نتوانستم پاسخ مناسبی تولید کنم.",
                    "requires_follow_up": False
                }
            
            logger.info(f"Message processed successfully for user {user_id}")

            # Save user message to conversation
            from database.models import Message, MessageRole
            user_message = Message(
                role=MessageRole.USER,
                content=message,
                timestamp=datetime.now(),
                emotion_detected=therapy_response.emotion_detected
            )
            await db_client.add_message_to_conversation(conversation_id, user_message)
            
            # Save bot response to conversation  
            bot_message = Message(
                role=MessageRole.ASSISTANT,
                content=therapy_response.response_text,
                timestamp=datetime.now()
            )
            await db_client.add_message_to_conversation(conversation_id, bot_message)
            logger.info(f"Messages saved to conversation {conversation_id}")
            
            return {
                "success": True,
                "response": therapy_response.response_text,
                "requires_follow_up": therapy_response.requires_follow_up,
                "follow_up_question": therapy_response.follow_up_question,
                "emotion_detected": therapy_response.emotion_detected,
                "personality_updates": therapy_response.personality_updates
            }
            
        except Exception as e:
            logger.error(f"Error processing message through graph for user {user_id}: {e}")
            return {
                "success": False,
                "response": "متأسفم، مشکلی در پردازش پیام شما پیش آمده.",
                "requires_follow_up": False
            }

# Global therapy graph instance
therapy_graph = TherapyGraph()