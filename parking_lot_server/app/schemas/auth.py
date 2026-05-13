from datetime import datetime
from pydantic import BaseModel
import uuid


class SignupRequest(BaseModel):
    username: str
    email: str
    password: str


class SignupResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
