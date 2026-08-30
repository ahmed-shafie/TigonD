from app.application.use_cases.platform_catalog import PlatformCatalog


def test_mvp_connector_and_runtime_catalog_is_complete():
    catalog = PlatformCatalog()
    connectors = {item.key for item in catalog.registry.connectors}
    runtimes = {item.key for item in catalog.registry.runtimes}
    assert {"postgresql", "oracle", "sqlserver", "mysql", "csv", "excel", "s3", "rest"}.issubset(connectors)
    assert {"nifi", "airbyte", "dlt", "kafka_debezium"} == runtimes


def test_lineage_is_connected_source_to_target():
    graph = PlatformCatalog().lineage()
    assert graph.nodes[0].kind == "source"
    assert graph.nodes[-1].kind == "target"
    assert len(graph.edges) == len(graph.nodes) - 1


def test_all_mvp_workspaces_are_available():
    names = {item.workspace for item in PlatformCatalog().workspaces()}
    assert names == {"operations", "data_quality", "governance", "administration"}

