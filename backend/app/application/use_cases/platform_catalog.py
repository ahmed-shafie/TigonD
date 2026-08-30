from ...infrastructure.connectors import CapabilityRegistry
from ...models import LineageEdge, LineageGraph, LineageNode, WorkspaceSummary


class PlatformCatalog:
    def __init__(self, registry: CapabilityRegistry | None = None):
        self.registry = registry or CapabilityRegistry()

    def lineage(self) -> LineageGraph:
        nodes = [LineageNode(node_id="crm", kind="source", label="CRM PostgreSQL"), LineageNode(node_id="customers", kind="dataset", label="public.customers"), LineageNode(node_id="pipeline", kind="pipeline", label="Customer ingestion"), LineageNode(node_id="quality", kind="quality_gate", label="Customer quality rules"), LineageNode(node_id="bronze", kind="target", label="Bronze customers")]
        edges = [LineageEdge(source="crm", target="customers", operation="contains"), LineageEdge(source="customers", target="pipeline", operation="extract"), LineageEdge(source="pipeline", target="quality", operation="validate"), LineageEdge(source="quality", target="bronze", operation="load")]
        return LineageGraph(nodes=nodes, edges=edges)

    def workspaces(self) -> list[WorkspaceSummary]:
        return [
            WorkspaceSummary(workspace="operations", cards={"running": 1, "failed": 0, "queued": 12}, actions=["Review incidents", "Request approved retry"]),
            WorkspaceSummary(workspace="data_quality", cards={"average_score": 92, "open_rules": 8, "quarantined": 0}, actions=["Review rule evidence", "Approve quality threshold"]),
            WorkspaceSummary(workspace="governance", cards={"pii_columns": 1, "lineage_nodes": 5, "open_reviews": 0}, actions=["Inspect lineage", "Review PII classification"]),
            WorkspaceSummary(workspace="administration", cards={"connectors": len(self.registry.connectors), "runtimes": len(self.registry.runtimes), "skills": 7}, actions=["Configure runtime", "Manage role policy"]),
        ]

