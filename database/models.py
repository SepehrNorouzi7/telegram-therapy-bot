from pydantic import BaseModel, Field, ConfigDict, validator
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from bson import ObjectId

# Helper function to convert ObjectId to string
def convert_objectid_to_str(v):
    if isinstance(v, ObjectId):
        return str(v)
    return v

class CommunicationStyle(str, Enum):
    """Communication style types"""
    DIRECT = "direct"
    SUPPORTIVE = "supportive" 
    ANALYTICAL = "analytical"
    EMPATHETIC = "empathetic"

class EmotionalState(str, Enum):
    """Emotional state types"""
    STABLE = "stable"
    ANXIOUS = "anxious"
    DEPRESSED = "depressed"
    EXCITED = "excited"
    CONFUSED = "confused"

class TherapyApproach(str, Enum):
    """Therapy approach types"""
    CBT = "CBT"
    HUMANISTIC = "humanistic"
    BEHAVIORAL = "behavioral"
    PSYCHODYNAMIC = "psychodynamic"

class MessageRole(str, Enum):
    """Message role types"""
    USER = "user"
    ASSISTANT = "assistant"

class MemoryType(str, Enum):
    """Memory type classification"""
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"

class ImportanceLevel(str, Enum):
    """Context importance levels"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class PersonalityTraits(BaseModel):
    """User personality traits model"""
    openness: float = Field(default=0.5, ge=0.0, le=1.0)
    conscientiousness: float = Field(default=0.5, ge=0.0, le=1.0)
    extraversion: float = Field(default=0.5, ge=0.0, le=1.0)
    agreeableness: float = Field(default=0.5, ge=0.0, le=1.0)
    neuroticism: float = Field(default=0.5, ge=0.0, le=1.0)
    communication_style: CommunicationStyle = Field(default=CommunicationStyle.SUPPORTIVE)
    emotional_state: EmotionalState = Field(default=EmotionalState.STABLE)
    preferred_therapy_approach: TherapyApproach = Field(default=TherapyApproach.HUMANISTIC)

class Message(BaseModel):
    """Individual message model"""
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    emotion_detected: Optional[str] = None
    context_importance: ImportanceLevel = Field(default=ImportanceLevel.MEDIUM)

class User(BaseModel):
    """User model for MongoDB"""
    model_config = ConfigDict(populate_by_name=True)
    
    id: str = Field(alias="_id", default=None)  # Telegram user ID
    first_name: str
    username: Optional[str] = None
    personality_traits: PersonalityTraits = Field(default_factory=PersonalityTraits)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    session_count: int = Field(default=0)
    
    @validator('id', pre=True)
    def convert_id(cls, v):
        return convert_objectid_to_str(v)

class Conversation(BaseModel):
    """Conversation model for MongoDB"""
    model_config = ConfigDict(populate_by_name=True)
    
    id: Optional[str] = Field(alias="_id", default=None)
    user_id: str
    messages: List[Message] = Field(default_factory=list)
    session_summary: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    
    @validator('id', pre=True)
    def convert_id(cls, v):
        return convert_objectid_to_str(v)

class Memory(BaseModel):
    """Memory model for MongoDB"""
    model_config = ConfigDict(populate_by_name=True)
    
    id: Optional[str] = Field(alias="_id", default=None)
    user_id: str
    memory_type: MemoryType
    content: str
    importance_score: float = Field(ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.now)
    last_accessed: datetime = Field(default_factory=datetime.now)
    access_count: int = Field(default=0)
    
    @validator('id', pre=True)
    def convert_id(cls, v):
        return convert_objectid_to_str(v)

class UserAnalysisResult(BaseModel):
    """Result of user analysis node"""
    user_id: str
    current_message: str
    personality_insights: Dict[str, Any]
    emotional_state: EmotionalState
    context_from_memory: List[str]
    requires_follow_up_question: bool = False
    follow_up_question: Optional[str] = None

class TherapyResponse(BaseModel):
    """Response from therapy graph"""
    response_text: str
    requires_follow_up: bool = False
    follow_up_question: Optional[str] = None
    emotion_detected: Optional[str] = None
    personality_updates: Optional[Dict[str, float]] = None
    memory_importance: ImportanceLevel = ImportanceLevel.MEDIUM