import ast
from pathlib import Path

from app.application.use_cases.skills import BrowseSkills
from app.infrastructure.skills import BuiltinSkillRegistry


BACKEND = Path(__file__).parents[1] / "app"


def test_domain_has_no_framework_or_infrastructure_imports():
    forbidden = {"fastapi", "httpx", "psycopg", "app.infrastructure", "app.presentation"}
    for path in (BACKEND / "domain").glob("*.py"):
        tree = ast.parse(path.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any(name == item or name.startswith(f"{item}.") for name in imported for item in forbidden)


def test_main_is_a_composition_root_and_feature_routes_are_split():
    source = (BACKEND / "main.py").read_text()
    assert "include_router(skills_router)" in source
    assert "include_router(assistant_router)" in source
    assert 'def assistant_chat(' not in source


def test_skill_catalog_is_role_filtered_and_approval_safe():
    use_case = BrowseSkills(BuiltinSkillRegistry())
    quality_keys = {skill.key for skill in use_case.list_for({"quality"})}
    admin_skills = use_case.list_for({"administrator"})
    assert "source-profile" in quality_keys
    assert "nifi-deploy" not in quality_keys
    assert all(skill.requires_approval for skill in admin_skills if skill.risk_level == "high")
    assert "incident-diagnosis" not in {skill.key for skill in admin_skills}
