from ..domain.skills import SkillDefinition


class BuiltinSkillRegistry:
    """Versioned, allow-listed capabilities. Skills never receive credentials directly."""

    _skills = (
        SkillDefinition("source-profile", "Source Profiler", "Run bounded EDA and column-quality profiling.", "source-intelligence", "1.0.0", "low", ("administrator", "developer", "quality")),
        SkillDefinition("pii-detection", "PII Detection", "Detect likely sensitive columns from profile evidence.", "governance", "1.0.0", "medium", ("administrator", "developer", "quality", "governance")),
        SkillDefinition("runtime-recommendation", "Runtime Advisor", "Compare NiFi, Airbyte, dlt and CDC using source evidence.", "design", "1.0.0", "low", ("administrator", "developer", "operator", "quality", "governance")),
        SkillDefinition("pipeline-design", "Pipeline Designer", "Create a reviewable pipeline proposal from a requirement.", "design", "1.0.0", "medium", ("administrator", "developer")),
        SkillDefinition("proposal-validation", "Proposal Validator", "Check mappings, watermarks, quality gates and runtime constraints.", "safety", "1.0.0", "low", ("administrator", "developer", "quality")),
        SkillDefinition("nifi-compile", "NiFi Compiler", "Compile an approved proposal into a versioned NiFi flow specification.", "execution", "1.0.0", "high", ("administrator", "developer"), requires_approval=True),
        SkillDefinition("nifi-deploy", "NiFi Deployment", "Deploy a compiled flow using isolated runtime secrets.", "execution", "1.0.0", "high", ("administrator", "developer"), requires_approval=True),
        SkillDefinition("incident-diagnosis", "Incident Diagnosis", "Explain failures and propose remediation from operational evidence.", "operations", "0.1.0", "medium", ("administrator", "developer", "operator"), implemented=False, enabled=False),
    )

    def all(self) -> tuple[SkillDefinition, ...]:
        return self._skills

    def get(self, key: str) -> SkillDefinition:
        try:
            return next(skill for skill in self._skills if skill.key == key)
        except StopIteration as exc:
            raise KeyError(key) from exc

