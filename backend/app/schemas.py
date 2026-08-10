from typing import Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=63, pattern=r"^[a-z][a-z0-9_-]+$")
    displayName: str | None = Field(default=None, max_length=100)
    description: str = Field(default="", max_length=500)


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    projectName: str = Field(min_length=2, max_length=63)


class AssetGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1000)


class AssetGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1000)


class AssetCreate(BaseModel):
    group_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    asset_type: Literal["Image", "Video", "Audio"]
    name: str | None = Field(default=None, max_length=128)


class AssetUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
