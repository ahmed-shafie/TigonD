from dataclasses import dataclass

from ...assistant import AssistantEngine
from ...models import AssistantRequest, AssistantResponse
from ..ports.repositories import AssistantRepository


@dataclass(slots=True)
class AskAssistant:
    repository: AssistantRepository
    engine: AssistantEngine

    def execute(self, request: AssistantRequest, actor: str) -> AssistantResponse:
        context = self.repository.assistant_context(request.assessment_id, request.deployment_id)
        response = self.engine.answer(request, context)
        return self.repository.save_assistant_exchange(request, response, actor)

