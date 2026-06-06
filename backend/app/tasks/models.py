"""Task data models."""

from enum import Enum
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TaskType(str, Enum):
    general = "general"
    research = "research"
    code = "code"
    document = "document"
    agent = "agent"


class TaskCreate(BaseModel):
    title: str
    description: str
    type: TaskType = TaskType.general
    session_id: Optional[str] = None


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: TaskType = TaskType.general
    title: str
    description: str
    status: TaskStatus = TaskStatus.queued
    progress: int = 0
    progress_text: str = ""
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    session_id: Optional[str] = None


class TaskUpdate(BaseModel):
    status: Optional[TaskStatus] = None
    progress: Optional[int] = None
    progress_text: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
