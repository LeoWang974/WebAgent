from app.schemas.base import ApiModel
from app.schemas.session import SkillKey


class Skill(ApiModel):
    key: SkillKey
    name: str
    description: str
    version: str
    enabled: bool
    is_default: bool | None = None
    last_updated_at: str | None = None
