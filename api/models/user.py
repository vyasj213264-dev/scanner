"""
User models for authentication.
"""
from datetime import datetime
from typing import Optional, Union
from pydantic import BaseModel


class User(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    google_id: Optional[str] = None
    plan: str = "free"
    created_at: Optional[Union[str, datetime]] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
