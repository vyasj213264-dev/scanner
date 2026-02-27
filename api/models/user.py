"""
User models for authentication.
"""
from typing import Optional
from pydantic import BaseModel


class User(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    google_id: Optional[str] = None
    plan: str = "free"
    created_at: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
