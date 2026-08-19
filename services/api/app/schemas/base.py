# File purpose: Defines Pydantic API contracts for base.
# Main declarations: to_camel converts camel; ApiModel defines api model state or behavior.

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
