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
    plan: Optional[str] = "free"
    is_admin: Optional[bool] = False
    session_id: Optional[int] = None
    created_at: Optional[Union[str, datetime]] = None

class UserSession(BaseModel):
    id: int
    user_id: int
    login_time: Optional[Union[str, datetime]] = None
    last_active_time: Optional[Union[str, datetime]] = None

class UserEvent(BaseModel):
    event_type: str
    event_data: Optional[str] = None



class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
