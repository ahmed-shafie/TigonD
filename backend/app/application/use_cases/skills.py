from dataclasses import dataclass

from ..ports.skills import SkillRegistry
from ...domain.skills import SkillDefinition


@dataclass(slots=True)
class BrowseSkills:
    registry: SkillRegistry

    def list_for(self, roles: set[str]) -> list[SkillDefinition]:
        return [skill for skill in self.registry.all() if skill.enabled and skill.visible_to(roles)]

    def get_for(self, key: str, roles: set[str]) -> SkillDefinition:
        skill = self.registry.get(key)
        if not skill.enabled or not skill.visible_to(roles):
            raise PermissionError(key)
        return skill

