from app.services.knowledge.postgres_store import PostgresKnowledgeStore


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str, parameters=None) -> None:  # noqa: ANN001
        self.statements.append(" ".join(statement.split()).lower())


class RecordingConnection:
    def __init__(self, cursor: RecordingCursor) -> None:
        self._cursor = cursor

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, *args) -> None:  # noqa: ANN002
        return None

    def cursor(self):  # noqa: ANN201
        return CursorContext(self._cursor)


class CursorContext:
    def __init__(self, cursor: RecordingCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> RecordingCursor:
        return self._cursor

    def __exit__(self, *args) -> None:  # noqa: ANN002
        return None


def test_tariff_schema_preserves_pages_rules_packages_and_safe_publication() -> None:
    cursor = RecordingCursor()

    PostgresKnowledgeStore("postgresql://unused")._ensure_schema(cursor)  # noqa: SLF001

    sql = "\n".join(cursor.statements)
    assert "create table if not exists knowledge_documents" not in sql
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


def test_tariff_inventory_sync_is_idempotent(monkeypatch) -> None:  # noqa: ANN001
    from app.services.knowledge.tariff_catalog import TariffCatalogLoader

    cursor = RecordingCursor()
    store = PostgresKnowledgeStore("postgresql://unused")
    monkeypatch.setattr(store, "_connect", lambda: RecordingConnection(cursor))

    store.sync_tariff_inventory(TariffCatalogLoader().load_inventory())

    sql = "\n".join(cursor.statements)
    assert "on conflict (section_id) do update" in sql
    assert "on conflict (source_id, page_number) do update" in sql
    assert sql.count("insert into knowledge_pages") == 25


def test_tariff_entry_sync_is_idempotent(monkeypatch) -> None:  # noqa: ANN001
    from app.services.knowledge.tariff_catalog import TariffCatalogLoader

    cursor = RecordingCursor()
    store = PostgresKnowledgeStore("postgresql://unused")
    monkeypatch.setattr(store, "_connect", lambda: RecordingConnection(cursor))

    catalog = TariffCatalogLoader().load_entries()
    store.sync_tariff_entries(catalog)

    sql = "\n".join(cursor.statements)
    assert "on conflict (tariff_id) do update" in sql
    assert sql.count("insert into tariff_entries") == len(catalog["entries"])


def test_tariff_auxiliary_sync_is_idempotent(monkeypatch) -> None:  # noqa: ANN001
    from app.services.knowledge.tariff_catalog import TariffCatalogLoader

    cursor = RecordingCursor()
    store = PostgresKnowledgeStore("postgresql://unused")
    monkeypatch.setattr(store, "_connect", lambda: RecordingConnection(cursor))
    catalog = TariffCatalogLoader().load_auxiliary()

    store.sync_tariff_auxiliary(catalog)

    sql = "\n".join(cursor.statements)
    assert sql.count("insert into service_packages") == 50
    assert sql.count("insert into package_items") == 78
    assert sql.count("insert into tariff_rules") == 56
    assert sql.count("insert into tariff_entry_rules") == 10
