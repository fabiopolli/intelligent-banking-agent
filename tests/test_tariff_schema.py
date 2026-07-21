from app.services.knowledge.postgres_store import PostgresKnowledgeStore


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str, parameters=None) -> None:  # noqa: ANN001
        self.statements.append(" ".join(statement.split()).lower())


def test_tariff_schema_preserves_pages_rules_packages_and_safe_publication() -> None:
    cursor = RecordingCursor()

    PostgresKnowledgeStore("postgresql://unused")._ensure_schema(cursor)  # noqa: SLF001

    sql = "\n".join(cursor.statements)
    for table in (
        "knowledge_facts",
        "fact_evidence",
        "knowledge_sections",
        "knowledge_pages",
        "tariff_entries",
        "tariff_rules",
        "tariff_entry_rules",
        "service_packages",
        "package_items",
    ):
        assert f"create table if not exists {table}" in sql
    assert "status <> 'published' or reviewed_at is not null" in sql
    assert "foreign key (source_id, page_number)" in sql
    assert "tariff_entries_lookup_idx" in sql
    assert "tariff_entries_dimensions_idx" in sql
    assert "knowledge_facts_search_idx" in sql
