from typing import List, Optional, Dict, Any
from typing_extensions import TypedDict
from datetime import datetime

from database.models import PersonalityTraits, UserAnalysisResult, TherapyResponse

class TherapyState(TypedDict):
    """State object for therapy conversation graph"""
    
    # User Information
    user_id: str
    current_message: str
    conversation_history: List[Dict[str, Any]]
    
    # User Profile
    user_personality: Optional[PersonalityTraits]
    memory_context: List[str]
    
    # Processing Results
    analysis_result: Optional[UserAnalysisResult]
    therapy_response: Optional[TherapyResponse]
    
    # Metadata
    processed_at: datetime
    message_count: int