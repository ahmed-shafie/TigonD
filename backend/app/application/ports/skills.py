from typing import Protocol

from ...domain.skills import SkillDefinition


class SkillRegistry(Protocol):
    def all(self) -> tuple[SkillDefinition, ...]: ...

    def get(self, key: str) -> SkillDefinition: ...

