from fastapi import APIRouter, Depends, HTTPException

from ....application.use_cases.skills import BrowseSkills
from ....auth import Principal, require_roles
from ....dependencies import get_skill_browser


router = APIRouter(prefix="/api/v1/skills", tags=["skills"])
VISIBLE_ROLES = ("administrator", "developer", "operator", "quality", "governance")


@router.get("")
def list_skills(
    principal: Principal = Depends(require_roles(*VISIBLE_ROLES)),
    browser: BrowseSkills = Depends(get_skill_browser),
) -> list[dict[str, object]]:
    return [skill.to_dict() for skill in browser.list_for(principal.roles)]


@router.get("/{skill_key}")
def get_skill(
    skill_key: str,
    principal: Principal = Depends(require_roles(*VISIBLE_ROLES)),
    browser: BrowseSkills = Depends(get_skill_browser),
) -> dict[str, object]:
    try:
        return browser.get_for(skill_key, principal.roles).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Skill is not available for this role") from exc
