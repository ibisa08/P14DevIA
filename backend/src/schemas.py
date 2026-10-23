"""Schémas d'entrée/sortie de l'API, séparés des modèles de table.

Les réponses ne passent que par ces schémas : `hashed_password` ne peut pas fuiter.
"""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: int
    email: str
