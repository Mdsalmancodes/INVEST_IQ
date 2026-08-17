from datetime import datetime
from pydantic import BaseModel, Field
from uuid import uuid4


class ModelVersion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    model_name: str
    version: str
    accuracy: float | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)