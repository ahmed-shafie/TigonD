from ..models import ConnectorCapability, RuntimeCapability


class CapabilityRegistry:
    connectors = (
        ConnectorCapability(key="postgresql", name="PostgreSQL", category="database", modes=["batch", "incremental", "cdc"], status="ready", required_fields=["host", "port", "database", "username"], secret_fields=["password"]),
        ConnectorCapability(key="oracle", name="Oracle", category="database", modes=["batch", "incremental", "cdc"], status="requires_driver", required_fields=["host", "port", "service_name", "username"], secret_fields=["password"]),
        ConnectorCapability(key="sqlserver", name="SQL Server", category="database", modes=["batch", "incremental", "cdc"], status="requires_driver", required_fields=["host", "port", "database", "username"], secret_fields=["password"]),
        ConnectorCapability(key="mysql", name="MySQL", category="database", modes=["batch", "incremental", "cdc"], status="requires_driver", required_fields=["host", "port", "database", "username"], secret_fields=["password"]),
        ConnectorCapability(key="csv", name="CSV", category="file", modes=["batch"], status="ready", required_fields=["path"], secret_fields=[]),
        ConnectorCapability(key="excel", name="Excel", category="file", modes=["batch"], status="ready", required_fields=["path", "sheet"], secret_fields=[]),
        ConnectorCapability(key="s3", name="S3 / MinIO", category="object_storage", modes=["batch", "incremental"], status="requires_runtime", required_fields=["endpoint", "bucket", "access_key"], secret_fields=["secret_key"]),
        ConnectorCapability(key="rest", name="REST API", category="saas", modes=["batch", "incremental"], status="ready", required_fields=["base_url"], secret_fields=["token"]),
    )
    runtimes = (
        RuntimeCapability(key="nifi", supports=["visual flows", "batch", "incremental", "quality routing"], execution_status="ready", health_endpoint="/api/v1/runtimes/nifi/health"),
        RuntimeCapability(key="airbyte", supports=["packaged connectors", "batch", "incremental", "cdc"], execution_status="adapter_ready_requires_runtime", health_endpoint="/api/v1/runtimes/airbyte/health"),
        RuntimeCapability(key="dlt", supports=["pipeline as code", "batch", "incremental", "schema evolution"], execution_status="adapter_ready_requires_runtime", health_endpoint="/api/v1/runtimes/dlt/health"),
        RuntimeCapability(key="kafka_debezium", supports=["streaming", "cdc", "schema registry"], execution_status="adapter_ready_requires_runtime", health_endpoint="/api/v1/runtimes/kafka-debezium/health"),
    )

