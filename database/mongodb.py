from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor
from bson import ObjectId
from config import Config
from database.models import User, Conversation, Memory, Message, PersonalityTraits, MemoryType
from utils.logger import logger

class MongoDBClient:
    """MongoDB client for therapy bot"""
    
    def __init__(self):
        self.client = None
        self.db = None
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.connect()
    
    def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = MongoClient(Config.MONGODB_URI)
            self.db = self.client[Config.DATABASE_NAME]
            
            # Test connection
            self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
            
            # Create indexes
            self._create_indexes()
            
        except ConnectionFailure as e:
            logger.error("Failed to connect to MongoDB", error=e)
            raise
    
    def _create_indexes(self):
        """Create database indexes for better performance"""
        try:      
            # Conversations collection indexes
            self.db[Config.CONVERSATIONS_COLLECTION].create_index("user_id")
            self.db[Config.CONVERSATIONS_COLLECTION].create_index("created_at")
            
            # Memory collection indexes
            self.db[Config.MEMORY_COLLECTION].create_index("user_id")
            self.db[Config.MEMORY_COLLECTION].create_index("memory_type")
            self.db[Config.MEMORY_COLLECTION].create_index("importance_score")
            self.db[Config.MEMORY_COLLECTION].create_index("last_accessed")
            
            logger.info("Database indexes created successfully")
            
        except Exception as e:
            logger.error("Failed to create indexes", error=e)
    
    async def _run_in_executor(self, func, *args):
        """Run database operation in thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args)
    
    # User Operations
    async def create_user(self, user_id: str, first_name: str, username: str = None) -> User:
        """Create a new user"""
        def _create():
            user_data = {
                "_id": user_id,
                "first_name": first_name,
                "username": username,
                "personality_traits": PersonalityTraits().dict(),
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "session_count": 0
            }
            
            try:
                result = self.db[Config.USERS_COLLECTION].insert_one(user_data)
                logger.log_database_operation("CREATE", Config.USERS_COLLECTION, user_id)
                return User(**user_data)
            except DuplicateKeyError:
                logger.warning(f"User {user_id} already exists")
                return self.get_user_sync(user_id)
        
        return await self._run_in_executor(_create)
    
    def get_user_sync(self, user_id: str) -> Optional[User]:
        """Get user by ID synchronously (for internal use)"""
        user_data = self.db[Config.USERS_COLLECTION].find_one({"_id": user_id})
        if user_data:
            return User(**user_data)
        return None
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        def _get():
            user_data = self.db[Config.USERS_COLLECTION].find_one({"_id": user_id})
            if user_data:
                return User(**user_data)
            return None
        
        return await self._run_in_executor(_get)
    
    async def update_user_personality(self, user_id: str, personality_traits: PersonalityTraits) -> bool:
        """Update user personality traits"""
        def _update():
            result = self.db[Config.USERS_COLLECTION].update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "personality_traits": personality_traits.dict(),
                        "updated_at": datetime.now()
                    }
                }
            )
            logger.log_database_operation("UPDATE_PERSONALITY", Config.USERS_COLLECTION, user_id)
            return result.modified_count > 0
        
        return await self._run_in_executor(_update)
    
    async def increment_session_count(self, user_id: str) -> bool:
        """Increment user session count"""
        def _increment():
            result = self.db[Config.USERS_COLLECTION].update_one(
                {"_id": user_id},
                {"$inc": {"session_count": 1}}
            )
            return result.modified_count > 0
        
        return await self._run_in_executor(_increment)
    
    # Conversation Operations
    async def create_conversation(self, user_id: str) -> str:
        """Create a new conversation"""
        def _create():
            conversation_data = {
                "user_id": user_id,
                "messages": [],
                "session_summary": None,
                "created_at": datetime.now()
            }
            
            result = self.db[Config.CONVERSATIONS_COLLECTION].insert_one(conversation_data)
            conversation_id = str(result.inserted_id)
            logger.log_database_operation("CREATE", Config.CONVERSATIONS_COLLECTION, user_id)
            return conversation_id
        
        return await self._run_in_executor(_create)
    
    async def add_message_to_conversation(self, conversation_id: str, message: Message) -> bool:
        """Add message to conversation"""
        def _add():
            result = self.db[Config.CONVERSATIONS_COLLECTION].update_one(
                {"_id": ObjectId(conversation_id)},
                {"$push": {"messages": message.dict()}}
            )
            return result.modified_count > 0
        
        return await self._run_in_executor(_add)
    
    async def get_recent_conversations(self, user_id: str, limit: int = 5) -> List[Conversation]:
        """Get recent conversations for a user"""
        def _get():
            conversations = self.db[Config.CONVERSATIONS_COLLECTION].find(
                {"user_id": user_id}
            ).sort("created_at", -1).limit(limit)
            
            return [Conversation(**conv) for conv in conversations]
        
        return await self._run_in_executor(_get)
    
    # Memory Operations
    async def store_memory(self, user_id: str, content: str, memory_type: MemoryType, 
                          importance_score: float) -> str:
        """Store a memory"""
        def _store():
            memory_data = {
                "user_id": user_id,
                "memory_type": memory_type.value,
                "content": content,
                "importance_score": importance_score,
                "created_at": datetime.now(),
                "last_accessed": datetime.now(),
                "access_count": 0
            }
            
            result = self.db[Config.MEMORY_COLLECTION].insert_one(memory_data)
            memory_id = str(result.inserted_id)
            logger.log_database_operation("STORE_MEMORY", Config.MEMORY_COLLECTION, user_id)
            return memory_id
        
        return await self._run_in_executor(_store)
    
    async def get_relevant_memories(self, user_id: str, memory_type: MemoryType = None, 
                                   limit: int = 10) -> List[Memory]:
        """Get relevant memories for a user"""
        def _get():
            query = {"user_id": user_id}
            if memory_type:
                query["memory_type"] = memory_type.value
            
            memories = self.db[Config.MEMORY_COLLECTION].find(query).sort([
                ("importance_score", -1),
                ("last_accessed", -1)
            ]).limit(limit)
            
            return [Memory(**mem) for mem in memories]
        
        return await self._run_in_executor(_get)
    
    async def update_memory_access(self, memory_id: str) -> bool:
        """Update memory access information"""
        def _update():
            result = self.db[Config.MEMORY_COLLECTION].update_one(
                {"_id": memory_id},
                {
                    "$set": {"last_accessed": datetime.now()},
                    "$inc": {"access_count": 1}
                }
            )
            return result.modified_count > 0
        
        return await self._run_in_executor(_update)
    
    async def cleanup_old_short_term_memories(self, user_id: str, days: int = 7) -> int:
        """Clean up old short-term memories"""
        def _cleanup():
            cutoff_date = datetime.now() - timedelta(days=days)
            result = self.db[Config.MEMORY_COLLECTION].delete_many({
                "user_id": user_id,
                "memory_type": MemoryType.SHORT_TERM.value,
                "created_at": {"$lt": cutoff_date}
            })
            
            if result.deleted_count > 0:
                logger.log_database_operation("CLEANUP_MEMORIES", Config.MEMORY_COLLECTION, user_id)
            
            return result.deleted_count
        
        return await self._run_in_executor(_cleanup)
    
    def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            self.executor.shutdown(wait=True)
            logger.info("MongoDB connection closed")

# Global database instance
db_client = MongoDBClient()