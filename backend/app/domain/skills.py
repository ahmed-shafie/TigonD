from dataclasses import asdict, dataclass
from typing import Literal


RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    key: str
    name: str
    description: str
    category: str
    version: str
    risk_level: RiskLevel
    allowed_roles: tuple[str, ...]
    requires_approval: bool = False
    implemented: bool = True
    enabled: bool = True

    def visible_to(self, roles: set[str]) -> bool:
        return bool(roles.intersection(self.allowed_roles))

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["allowed_roles"] = list(self.allowed_roles)
        return payload

