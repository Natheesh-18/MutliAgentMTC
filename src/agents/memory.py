import redis
import os
from dotenv import load_dotenv

load_dotenv() 

class AgentMemoryOperation:
    def __init__(self):
        self.redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST"),
        port=int(os.getenv("REDIS_PORT")),
        db=0,
        decode_responses=True
    )

    def append_to_session_history(self, prompt_id: str, new_entry: str) -> None:
        """
        Append a new entry to the prompt history with space separation
        Creates new history if prompt doesn't exist
        """
        key = f"prompt:{prompt_id}:history"
        
        # Get current history or initialize empty
        current = self.redis_client.get(key) or ""
        
        # Append with space separation
        updated_history = f"{current} {new_entry}".strip()
        
        # Store back to Redis with expiration (e.g., 1 day)
        self.redis_client.setex(key, 86400, updated_history)

    def get_session_history(self, prompt_id: str) -> str:
        """
        Retrieve the full prompt history as a single string
        Returns empty string if no history exists
        """
        key = f"prompt:{prompt_id}:history"
        return self.redis_client.get(key) or ""
