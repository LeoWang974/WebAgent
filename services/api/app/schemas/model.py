from typing import Literal

from app.schemas.base import ApiModel

ModelProvider = Literal["sensenova", "openai_compatible", "custom"]


class ModelConfig(ApiModel):
    base_url: str | None = None
    id: str
    is_available: bool | None = None
    name: str
    provider: ModelProvider
    is_default: bool
    masked_api_key: str | None = None

