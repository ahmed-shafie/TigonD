from contextlib import contextmanager
from time import perf_counter

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .models import ColumnProfile, ConnectionTestResult, DataObject, PostgresConnection, TableProfile


class PostgresService:
    def __init__(self, timeout_seconds: int = 15, sample_rows: int = 10_000):
        self.timeout_seconds = timeout_seconds
        self.sample_rows = sample_rows

    @contextmanager
    def connect(self, config: PostgresConnection):
        with psycopg.connect(
            host=config.host,
            port=config.port,
            dbname=config.database,
            user=config.username,
            password=config.password.get_secret_value(),
            sslmode=config.sslmode,
            connect_timeout=self.timeout_seconds,
            row_factory=dict_row,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = %s", (self.timeout_seconds * 1000,))
            yield connection

    def test(self, config: PostgresConnection) -> ConnectionTestResult:
        started = perf_counter()
        with self.connect(config) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT current_database() AS database, version() AS version")
            row = cursor.fetchone()
        return ConnectionTestResult(
            ok=True,
            database=row["database"],
            server_version=row["version"],
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )

    def discover(self, config: PostgresConnection) -> list[DataObject]:
        query = """
            SELECT n.nspname AS schema_name, c.relname AS object_name,
                   CASE c.relkind WHEN 'v' THEN 'view' ELSE 'table' END AS object_type,
                   CASE WHEN c.reltuples < 0 THEN NULL ELSE c.reltuples::bigint END AS estimated_rows
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'p', 'v')
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
              AND n.nspname NOT LIKE 'pg_toast%'
            ORDER BY n.nspname, c.relname
        """
        with self.connect(config) as connection, connection.cursor() as cursor:
            cursor.execute(query)
            return [DataObject(**row) for row in cursor.fetchall()]

    def profile(self, config: PostgresConnection, schema_name: str, table_name: str) -> TableProfile:
        with self.connect(config) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name AS name, data_type, is_nullable = 'YES' AS nullable
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (schema_name, table_name),
            )
            columns = cursor.fetchall()
            if not columns:
                raise ValueError("Table was not found or is not accessible")

            table = sql.Identifier(schema_name, table_name)
            cursor.execute(sql.SQL("SELECT * FROM {} LIMIT %s").format(table), (self.sample_rows,))
            rows = cursor.fetchall()

        sampled_rows = len(rows)
        profiles: list[ColumnProfile] = []
        recommendations: list[str] = []
        for column in columns:
            values = [row[column["name"]] for row in rows]
            null_count = sum(value is None for value in values)
            non_null = [value for value in values if value is not None]
            distinct_count = len({str(value) for value in non_null})
            completeness = 100.0 if sampled_rows == 0 else 100 * (sampled_rows - null_count) / sampled_rows
            uniqueness = 100.0 if not non_null else 100 * distinct_count / len(non_null)
            if completeness < 95:
                recommendations.append(f"Review missing values in {column['name']} ({completeness:.1f}% complete).")
            profiles.append(ColumnProfile(
                **column,
                sampled_rows=sampled_rows,
                null_count=null_count,
                distinct_count=distinct_count,
                completeness=round(completeness, 2),
                uniqueness=round(uniqueness, 2),
            ))

        quality_score = round(sum(item.completeness for item in profiles) / len(profiles), 2)
        return TableProfile(
            source_id="",
            schema_name=schema_name,
            table_name=table_name,
            sampled_rows=sampled_rows,
            quality_score=quality_score,
            columns=profiles,
            recommendations=recommendations or ["No completeness issues detected in the sampled data."],
        )

