from fastapi import APIRouter, Depends

from ....application.use_cases.platform_catalog import PlatformCatalog
from ....auth import Principal, require_roles
from ....dependencies import get_platform_catalog
from ....models import ConnectorCapability, LineageGraph, RuntimeCapability, WorkspaceSummary


router = APIRouter(prefix="/api/v1/platform", tags=["mvp-platform"])
ROLES = ("administrator", "developer", "operator", "quality", "governance")


@router.get("/connectors", response_model=list[ConnectorCapability])
def connectors(catalog: PlatformCatalog = Depends(get_platform_catalog), _: Principal = Depends(require_roles(*ROLES))):
    return catalog.registry.connectors


@router.get("/runtimes", response_model=list[RuntimeCapability])
def runtimes(catalog: PlatformCatalog = Depends(get_platform_catalog), _: Principal = Depends(require_roles(*ROLES))):
    return catalog.registry.runtimes


@router.get("/lineage", response_model=LineageGraph)
def lineage(catalog: PlatformCatalog = Depends(get_platform_catalog), _: Principal = Depends(require_roles(*ROLES))):
    return catalog.lineage()


@router.get("/workspaces", response_model=list[WorkspaceSummary])
def workspaces(catalog: PlatformCatalog = Depends(get_platform_catalog), _: Principal = Depends(require_roles(*ROLES))):
    return catalog.workspaces()

