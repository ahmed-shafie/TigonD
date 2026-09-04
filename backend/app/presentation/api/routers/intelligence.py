from fastapi import APIRouter, Depends, Query, status

from ....application.use_cases.intelligence_loop import IntelligenceLoop
from ....auth import Principal, require_roles
from ....dependencies import get_intelligence_loop, get_repository
from ....models import (IncidentDiagnosis, IncidentSignal, IntelligenceMetrics,
                       MemoryRecord, MemoryRecordRequest, ProactiveInsight,
                       RecommendationFeedback)
from ....repository import SourceRepository


router = APIRouter(prefix="/api/v1/intelligence", tags=["diagnosis-memory"])
VIEWERS = ("administrator", "developer", "operator", "quality", "governance")


@router.post("/diagnoses", response_model=IncidentDiagnosis, status_code=status.HTTP_201_CREATED)
def diagnose(signal: IncidentSignal, repo: SourceRepository = Depends(get_repository), engine: IntelligenceLoop = Depends(get_intelligence_loop), principal: Principal = Depends(require_roles("administrator", "developer", "operator", "quality"))):
    result = engine.diagnose(signal)
    repo.audit(principal.username, "incident.diagnosed", "incident", result.incident_id, "success")
    return result


@router.get("/deployments/{deployment_id}/timeline", response_model=list[IncidentDiagnosis])
def timeline(deployment_id: str, engine: IntelligenceLoop = Depends(get_intelligence_loop), _: Principal = Depends(require_roles(*VIEWERS))):
    return engine.timeline(deployment_id)


@router.post("/memory", response_model=MemoryRecord, status_code=status.HTTP_201_CREATED)
def remember(request: MemoryRecordRequest, engine: IntelligenceLoop = Depends(get_intelligence_loop), _: Principal = Depends(require_roles("administrator", "developer", "operator", "quality", "governance"))):
    return engine.remember(request)


@router.get("/memory/search", response_model=list[MemoryRecord])
def recall(q: str = Query(min_length=2, max_length=300), scope: str | None = None, engine: IntelligenceLoop = Depends(get_intelligence_loop), _: Principal = Depends(require_roles(*VIEWERS))):
    return engine.recall(q, scope)


@router.post("/feedback", response_model=IntelligenceMetrics)
def feedback(request: RecommendationFeedback, engine: IntelligenceLoop = Depends(get_intelligence_loop), _: Principal = Depends(require_roles(*VIEWERS))):
    return engine.feedback(request)


@router.get("/metrics", response_model=IntelligenceMetrics)
def metrics(engine: IntelligenceLoop = Depends(get_intelligence_loop), _: Principal = Depends(require_roles(*VIEWERS))):
    return engine.metrics()


@router.get("/insights", response_model=list[ProactiveInsight])
def insights(engine: IntelligenceLoop = Depends(get_intelligence_loop), _: Principal = Depends(require_roles(*VIEWERS))):
    return engine.insights()

