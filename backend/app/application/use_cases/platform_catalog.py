from ...infrastructure.connectors import CapabilityRegistry
from ...models import LineageEdge, LineageGraph, LineageNode, WorkspaceSummary
from ..ports.repositories import IntelligenceStore, PlatformReader
from ..ports.skills import SkillRegistry


class PlatformCatalog:
    """Connector/runtime capabilities plus workspace and lineage views built from persisted evidence."""

    def __init__(self, reader: PlatformReader, incidents: IntelligenceStore, skills: SkillRegistry, registry: CapabilityRegistry | None = None):
        self.reader = reader
        self.incidents = incidents
        self.skills = skills
        self.registry = registry or CapabilityRegistry()

    def lineage(self) -> LineageGraph:
        nodes: list[LineageNode] = []
        edges: list[LineageEdge] = []
        seen: set[str] = set()

        def add(node_id: str, kind: str, label: str) -> str:
            if node_id not in seen:
                seen.add(node_id)
                nodes.append(LineageNode(node_id=node_id, kind=kind, label=label))
            return node_id

        for fact in self.reader.lineage_facts():
            source = add(f"source:{fact.source_id}", "source", fact.source_name)
            dataset = add(f"dataset:{fact.source_id}:{fact.schema_name}.{fact.table_name}", "dataset", f"{fact.schema_name}.{fact.table_name}")
            pipeline_label = f"{fact.table_name} ingestion" + (f" v{fact.deployment_version}" if fact.deployment_version else " (draft)")
            pipeline = add(f"pipeline:{fact.assessment_id}", "pipeline", pipeline_label)
            gate = add(f"quality:{fact.assessment_id}", "quality_gate", f"{fact.quality_gates} quality gates")
            target = add(f"target:{fact.target_pattern}", "target", fact.target_pattern)
            edges.extend([
                LineageEdge(source=source, target=dataset, operation="contains"),
                LineageEdge(source=dataset, target=pipeline, operation="extract"),
                LineageEdge(source=pipeline, target=gate, operation="validate"),
                LineageEdge(source=gate, target=target, operation="load"),
            ])
        return LineageGraph(nodes=nodes, edges=edges)

    def workspaces(self) -> list[WorkspaceSummary]:
        snapshot = self.reader.platform_snapshot()
        open_incidents = len(self.incidents.open_incidents())
        graph = self.lineage()
        deployments = snapshot.deployments
        return [
            WorkspaceSummary(workspace="operations", cards={"running": deployments.get("running", 0), "failed": deployments.get("failed", 0), "deployed": deployments.get("deployed", 0) + deployments.get("stopped", 0), "open_incidents": open_incidents}, actions=["Review incidents", "Request approved retry"]),
            WorkspaceSummary(workspace="data_quality", cards={"average_score": snapshot.average_quality_score, "assessments": snapshot.assessments, "active_rules": snapshot.quality_gates, "pending_reviews": snapshot.pending_reviews}, actions=["Review rule evidence", "Approve quality threshold"]),
            WorkspaceSummary(workspace="governance", cards={"pii_columns": snapshot.pii_columns, "lineage_nodes": len(graph.nodes), "connected_sources": snapshot.sources, "pending_reviews": snapshot.pending_reviews}, actions=["Inspect lineage", "Review PII classification"]),
            WorkspaceSummary(workspace="administration", cards={"connectors": len(self.registry.connectors), "runtimes": len(self.registry.runtimes), "skills": len(self.skills.all()), "connected_sources": snapshot.sources}, actions=["Configure runtime", "Manage role policy"]),
        ]
