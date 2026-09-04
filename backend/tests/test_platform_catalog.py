from app.application.use_cases.platform_catalog import PlatformCatalog
from app.infrastructure.intelligence_store import InMemoryIntelligenceStore
from app.infrastructure.skills import BuiltinSkillRegistry
from app.models import LineageFact, PlatformSnapshot


class FakeReader:
    def __init__(self, snapshot: PlatformSnapshot, facts: list[LineageFact]):
        self.snapshot = snapshot
        self.facts = facts

    def platform_snapshot(self) -> PlatformSnapshot:
        return self.snapshot

    def lineage_facts(self) -> list[LineageFact]:
        return self.facts


SNAPSHOT = PlatformSnapshot(sources=2, deployments={"running": 1, "generated": 2}, assessments=3,
                            pending_reviews=1, average_quality_score=88.9, pii_columns=3, quality_gates=6)
FACTS = [LineageFact(source_id="source-1", source_name="CRM Production", schema_name="public", table_name="customers",
                     assessment_id="assessment-1", target_pattern="bronze/public/customers", quality_gates=3, deployment_version=1)]


def catalog(snapshot: PlatformSnapshot = SNAPSHOT, facts: list[LineageFact] | None = None) -> PlatformCatalog:
    return PlatformCatalog(FakeReader(snapshot, FACTS if facts is None else facts), InMemoryIntelligenceStore(), BuiltinSkillRegistry())


def test_mvp_connector_and_runtime_catalog_is_complete():
    registry = catalog().registry
    connectors = {item.key for item in registry.connectors}
    runtimes = {item.key for item in registry.runtimes}
    assert {"postgresql", "oracle", "sqlserver", "mysql", "csv", "excel", "s3", "rest"}.issubset(connectors)
    assert {"nifi", "airbyte", "dlt", "kafka_debezium"} == runtimes


def test_lineage_is_connected_source_to_target():
    graph = catalog().lineage()
    assert graph.nodes[0].kind == "source"
    assert graph.nodes[0].label == "CRM Production"
    assert graph.nodes[-1].kind == "target"
    assert len(graph.edges) == len(graph.nodes) - 1


def test_lineage_is_empty_until_a_source_has_been_assessed():
    graph = catalog(facts=[]).lineage()
    assert graph.nodes == []
    assert graph.edges == []


def test_all_mvp_workspaces_are_available():
    names = {item.workspace for item in catalog().workspaces()}
    assert names == {"operations", "data_quality", "governance", "administration"}


def test_workspace_cards_report_persisted_evidence():
    cards = {item.workspace: item.cards for item in catalog().workspaces()}
    assert cards["operations"]["running"] == 1
    assert cards["operations"]["open_incidents"] == 0
    assert cards["data_quality"] == {"average_score": 88.9, "assessments": 3, "active_rules": 6, "pending_reviews": 1}
    assert cards["governance"]["pii_columns"] == 3
    assert cards["governance"]["lineage_nodes"] == 5
    assert cards["administration"]["connected_sources"] == 2


def test_workspace_cards_are_zero_on_an_empty_platform():
    empty = PlatformSnapshot(sources=0, deployments={}, assessments=0, pending_reviews=0,
                             average_quality_score=0, pii_columns=0, quality_gates=0)
    cards = {item.workspace: item.cards for item in catalog(empty, []).workspaces()}
    assert cards["operations"] == {"running": 0, "failed": 0, "deployed": 0, "open_incidents": 0}
    assert cards["data_quality"]["average_score"] == 0
    assert cards["governance"]["lineage_nodes"] == 0
