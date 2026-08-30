import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from ....application.use_cases.operational_actions import OperationalActionService
from ....auth import Principal, require_roles
from ....dependencies import get_nifi, get_operational_actions, get_repository
from ....domain.exceptions import ApprovalRequired, ResourceNotFound, ValidationBlocked
from ....models import (OperationalAction, OperationalActionApproval,
                       OperationalActionApprovalResult,
                       OperationalActionExecution, OperationalActionRequest)
from ....nifi import NiFiClient, NiFiError
from ....repository import SourceRepository


router = APIRouter(prefix="/api/v1/operational-actions", tags=["approved-actions"])


@router.post("", response_model=OperationalAction, status_code=status.HTTP_201_CREATED)
def propose_action(
    request: OperationalActionRequest,
    repo: SourceRepository = Depends(get_repository),
    service: OperationalActionService = Depends(get_operational_actions),
    principal: Principal = Depends(require_roles("administrator", "developer", "operator")),
):
    try:
        repo.get_deployment(request.deployment_id)
        action = service.propose(request, principal.username)
        repo.audit(principal.username, "operation.proposed", "operational_action", action.action_id, "success")
        return action
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Deployment not found") from exc


@router.get("/{action_id}", response_model=OperationalAction)
def get_action(
    action_id: str,
    service: OperationalActionService = Depends(get_operational_actions),
    _: Principal = Depends(require_roles("administrator", "developer", "operator", "governance")),
):
    try:
        return service.get(action_id)
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="Operational action not found") from exc


@router.post("/{action_id}/decision", response_model=OperationalActionApprovalResult)
def decide_action(
    action_id: str,
    decision: OperationalActionApproval,
    repo: SourceRepository = Depends(get_repository),
    service: OperationalActionService = Depends(get_operational_actions),
    principal: Principal = Depends(require_roles("administrator")),
):
    try:
        result = service.decide(action_id, decision.decision, principal.username)
        repo.audit(principal.username, f"operation.{decision.decision}", "operational_action", action_id, "success")
        return result
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="Operational action not found") from exc
    except ValidationBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{action_id}/execute", response_model=OperationalAction)
def execute_action(
    action_id: str,
    execution: OperationalActionExecution,
    repo: SourceRepository = Depends(get_repository),
    client: NiFiClient = Depends(get_nifi),
    service: OperationalActionService = Depends(get_operational_actions),
    principal: Principal = Depends(require_roles("administrator", "operator")),
):
    try:
        action = service.begin(action_id, execution.approval_token, execution.idempotency_key)
        if action.status in {"succeeded", "failed"}:
            return action
        deployment = repo.get_deployment(action.deployment_id)
        if action.action == "deploy":
            assessment = repo.get_assessment(deployment.assessment_id)
            source = repo.get_connection(assessment.source_id)
            secrets = {"JDBC_URL": f"jdbc:postgresql://{source.host}:{source.port}/{source.database}", "DB_USERNAME": source.username, "DB_PASSWORD": source.password.get_secret_value()}
            external_id = client.deploy(deployment.flow_spec, secrets)
            repo.update_deployment(action.deployment_id, "deployed", principal.username, external_id)
            result = "NiFi flow deployed in stopped state"
        else:
            if not deployment.external_flow_id:
                raise ValueError("Flow has not been deployed")
            target_state = "STOPPED" if action.action == "stop" else "RUNNING"
            client.set_state(deployment.external_flow_id, target_state)
            repo.update_deployment(action.deployment_id, "stopped" if target_state == "STOPPED" else "running", principal.username)
            result = f"NiFi flow changed to {target_state.lower()}"
        finished = service.finish(action_id, execution.idempotency_key, result)
        repo.audit(principal.username, "operation.executed", "operational_action", action_id, "success")
        return finished
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="Operational action not found") from exc
    except ApprovalRequired as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Deployment not found") from exc
    except (ValueError, NiFiError, httpx.HTTPError) as exc:
        failed = service.finish(action_id, execution.idempotency_key, "Execution failed", "Runtime state preserved; no automatic restart was attempted")
        repo.audit(principal.username, "operation.executed", "operational_action", action_id, "failed")
        return failed

