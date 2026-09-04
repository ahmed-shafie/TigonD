from fastapi import APIRouter, Depends

from ....application.use_cases.assistant import AskAssistant
from ....assistant import AssistantEngine
from ....auth import Principal, require_roles
from ....dependencies import get_assistant, get_repository
from ....models import AssistantRequest, AssistantResponse
from ....repository import SourceRepository


router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


@router.post("/chat", response_model=AssistantResponse)
def assistant_chat(
    request: AssistantRequest,
    repo: SourceRepository = Depends(get_repository),
    engine: AssistantEngine = Depends(get_assistant),
    principal: Principal = Depends(require_roles("administrator", "developer", "operator", "quality", "governance")),
):
    return AskAssistant(repo, engine).execute(request, principal.username)

