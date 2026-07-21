from __future__ import annotations

import json
import hashlib
import re

from app.services.knowledge.embedding import DeterministicTokenEmbedding
from app.services.knowledge.schemas import KnowledgeDocument, RetrievedKnowledge


class PostgresKnowledgeStore:
    def __init__(self, database_url: str, dimensions: int = 64) -> None:
        self._database_url = database_url
        self._embedding = DeterministicTokenEmbedding(dimensions)
        self._dimensions = dimensions

    def sync(
        self,
        documents: list[KnowledgeDocument],
        source_chunks: list[KnowledgeDocument] | None = None,
    ) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            self._ensure_schema(cursor)
            for document in documents:
                source_id = self._stable_id("source", document.source)
                cursor.execute(
                    """
                    INSERT INTO knowledge_sources (
                        source_id, source, source_type, version, status, content_hash
                    ) VALUES (%s, %s, 'curated-official', %s, %s, %s)
                    ON CONFLICT (source_id) DO UPDATE SET
                        source = EXCLUDED.source, version = EXCLUDED.version,
                        status = EXCLUDED.status, updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        source_id,
                        document.source,
                        document.version,
                        document.status,
                        hashlib.sha256(document.text.encode("utf-8")).hexdigest(),
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO knowledge_facts (
                        fact_id, title, source, content, product, topic, audience,
                        version, status, reviewed_at, limitations, embedding
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (fact_id) DO UPDATE SET
                        title = EXCLUDED.title, source = EXCLUDED.source, content = EXCLUDED.content,
                        product = EXCLUDED.product, topic = EXCLUDED.topic, audience = EXCLUDED.audience,
                        version = EXCLUDED.version, status = EXCLUDED.status,
                        reviewed_at = EXCLUDED.reviewed_at, limitations = EXCLUDED.limitations,
                        embedding = EXCLUDED.embedding, updated_at = CURRENT_TIMESTAMP
                    """,
                    (*self._document_values(document), self._vector_literal(self._embedding.embed(document.text))),
                )
                cursor.execute(
                    """
                    INSERT INTO fact_evidence (
                        fact_id, source_id, locator, evidence_text, content_hash
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (fact_id, source_id, locator) DO UPDATE SET
                        evidence_text = EXCLUDED.evidence_text,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        document.knowledge_id,
                        source_id,
                        self._evidence_locator(document.text),
                        document.text,
                        hashlib.sha256(document.text.encode("utf-8")).hexdigest(),
                    ),
                )
            chunks = source_chunks or []
            source_hashes = {
                source: hashlib.sha256(
                    "\n".join(item.text for item in chunks if item.source == source).encode("utf-8")
                ).hexdigest()
                for source in {item.source for item in chunks}
            }
            for chunk in chunks:
                source_id = self._stable_id("source", chunk.source)
                cursor.execute(
                    """
                    INSERT INTO knowledge_sources (
                        source_id, source, source_type, version, status, content_hash
                    ) VALUES (%s, %s, %s, %s, 'published', %s)
                    ON CONFLICT (source_id) DO UPDATE SET
                        source = EXCLUDED.source, source_type = EXCLUDED.source_type,
                        version = EXCLUDED.version, status = EXCLUDED.status,
                        content_hash = EXCLUDED.content_hash, updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        source_id,
                        chunk.source,
                        "official-web-snapshot" if chunk.source.startswith("http") else "official-pdf",
                        chunk.version,
                        source_hashes[chunk.source],
                    ),
                )
                chunk_id = self._stable_id("chunk", f"{chunk.source}|{chunk.title}|{chunk.text}")
                cursor.execute(
                    """
                    INSERT INTO knowledge_chunks (
                        chunk_id, source_id, title, content, page_number, embedding
                    ) VALUES (%s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        title = EXCLUDED.title, content = EXCLUDED.content,
                        page_number = EXCLUDED.page_number, embedding = EXCLUDED.embedding,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        chunk_id,
                        source_id,
                        chunk.title,
                        chunk.text,
                        self._page_number(chunk.title),
                        self._vector_literal(self._embedding.embed(chunk.text)),
                    ),
                )

    def load_documents(self) -> list[KnowledgeDocument]:
        with self._connect() as connection, connection.cursor() as cursor:
            self._ensure_schema(cursor)
            cursor.execute(
                """
                SELECT fact_id, title, source, content, product, topic, audience,
                       version, status, reviewed_at::text, limitations
                FROM knowledge_facts WHERE status = 'published' ORDER BY fact_id
                """
            )
            curated = [self._row_to_document(row) for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT c.title, s.source, c.content
                FROM knowledge_chunks c
                JOIN knowledge_sources s ON s.source_id = c.source_id
                WHERE s.status = 'published'
                ORDER BY c.chunk_id
                """
            )
            chunks = [KnowledgeDocument(title=row[0], source=row[1], text=row[2]) for row in cursor]
            return curated + chunks

    def sync_tariff_inventory(self, inventory: dict) -> None:
        source = str(inventory["source"])
        source_id = self._stable_id("source", source)
        with self._connect() as connection, connection.cursor() as cursor:
            self._ensure_schema(cursor)
            cursor.execute(
                """
                INSERT INTO knowledge_sources (
                    source_id, source, source_type, version, status, content_hash
                ) VALUES (%s, %s, 'official-pdf', %s, 'published', %s)
                ON CONFLICT (source_id) DO UPDATE SET
                    version = EXCLUDED.version, status = EXCLUDED.status,
                    content_hash = EXCLUDED.content_hash, updated_at = CURRENT_TIMESTAMP
                """,
                (source_id, source, inventory["catalog_version"], inventory["source_hash"]),
            )
            section_ids: dict[str, str] = {}
            for section in inventory["sections"]:
                section_id = self._stable_id("section", f"{source}|{section['code']}")
                section_ids[section["code"]] = section_id
                cursor.execute(
                    """
                    INSERT INTO knowledge_sections (
                        section_id, source_id, code, name, sort_order, page_start, page_end
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (section_id) DO UPDATE SET
                        name = EXCLUDED.name, sort_order = EXCLUDED.sort_order,
                        page_start = EXCLUDED.page_start, page_end = EXCLUDED.page_end
                    """,
                    (
                        section_id,
                        source_id,
                        section["code"],
                        section["name"],
                        section["sort_order"],
                        section["page_start"],
                        section["page_end"],
                    ),
                )
            for page in inventory["pages"]:
                cursor.execute(
                    """
                    INSERT INTO knowledge_pages (
                        source_id, page_number, section_id, content_hash,
                        extracted_text, review_status
                    ) VALUES (%s, %s, %s, %s, '', %s)
                    ON CONFLICT (source_id, page_number) DO UPDATE SET
                        section_id = EXCLUDED.section_id,
                        content_hash = EXCLUDED.content_hash,
                        review_status = EXCLUDED.review_status,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        source_id,
                        page["page_number"],
                        section_ids[page["section_code"]],
                        page["image_hash"],
                        page["review_status"],
                    ),
                )

    def sync_tariff_entries(self, catalog: dict) -> None:
        source = str(catalog["source"])
        source_id = self._stable_id("source", source)
        with self._connect() as connection, connection.cursor() as cursor:
            self._ensure_schema(cursor)
            for entry in catalog["entries"]:
                section_id = self._stable_id("section", f"{source}|{entry['section_code']}")
                cursor.execute(
                    """
                    INSERT INTO tariff_entries (
                        tariff_id, source_id, section_id, page_number, category,
                        service_code, service_name, delivery_channel, statement_code,
                        value_type, amount, minimum_amount, maximum_amount,
                        percentage_min, percentage_max, currency, billing_unit,
                        charging_event, dimensions, effective_from, status,
                        confidence, reviewed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (tariff_id) DO UPDATE SET
                        category = EXCLUDED.category, service_code = EXCLUDED.service_code,
                        service_name = EXCLUDED.service_name,
                        delivery_channel = EXCLUDED.delivery_channel,
                        statement_code = EXCLUDED.statement_code,
                        value_type = EXCLUDED.value_type, amount = EXCLUDED.amount,
                        minimum_amount = EXCLUDED.minimum_amount,
                        maximum_amount = EXCLUDED.maximum_amount,
                        percentage_min = EXCLUDED.percentage_min,
                        percentage_max = EXCLUDED.percentage_max,
                        currency = EXCLUDED.currency, billing_unit = EXCLUDED.billing_unit,
                        charging_event = EXCLUDED.charging_event,
                        dimensions = EXCLUDED.dimensions,
                        effective_from = EXCLUDED.effective_from, status = EXCLUDED.status,
                        confidence = EXCLUDED.confidence, reviewed_at = EXCLUDED.reviewed_at,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        entry["tariff_id"], source_id, section_id, entry["page_number"],
                        entry["category"], entry.get("service_code", ""), entry["service_name"],
                        entry.get("delivery_channel", ""), entry.get("statement_code", ""),
                        entry["value_type"], entry.get("amount"), entry.get("minimum_amount"),
                        entry.get("maximum_amount"), entry.get("percentage_min"),
                        entry.get("percentage_max"), entry.get("currency", "BRL"),
                        entry.get("billing_unit", ""), entry.get("charging_event", ""),
                        json.dumps(entry.get("dimensions", {}), ensure_ascii=False),
                        catalog["effective_from"], entry.get("status", "review_required"),
                        entry.get("confidence"), entry.get("reviewed_at"),
                    ),
                )
    def search(self, query: str, top_k: int = 6) -> list[RetrievedKnowledge]:
        query_vector = self._vector_literal(self._embedding.embed(query))
        with self._connect() as connection, connection.cursor() as cursor:
            self._ensure_schema(cursor)
            cursor.execute(
                """
                WITH searchable AS (
                    SELECT title, source, content, search_vector, embedding
                    FROM knowledge_facts WHERE status = 'published'
                    UNION ALL
                    SELECT c.title, s.source, c.content, c.search_vector, c.embedding
                    FROM knowledge_chunks c
                    JOIN knowledge_sources s ON s.source_id = c.source_id
                    WHERE s.status = 'published'
                )
                SELECT title, source, content,
                       4.0 * ts_rank_cd(search_vector, plainto_tsquery('simple', %s))
                       + GREATEST(0, 1 - (embedding <=> %s::vector)) AS score
                FROM searchable
                ORDER BY score DESC
                LIMIT %s
                """,
                (query, query_vector, top_k),
            )
            return [RetrievedKnowledge(title=row[0], source=row[1], text=row[2], score=float(row[3])) for row in cursor]

    def _connect(self):  # noqa: ANN202
        import psycopg

        return psycopg.connect(self._database_url)

    def _ensure_schema(self, cursor) -> None:  # noqa: ANN001
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_sources (
                source_id TEXT PRIMARY KEY,
                source TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS knowledge_facts (
                fact_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                product TEXT NOT NULL,
                topic TEXT NOT NULL,
                audience TEXT NOT NULL,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                reviewed_at DATE NOT NULL,
                limitations TEXT NOT NULL DEFAULT '',
                embedding vector({self._dimensions}) NOT NULL,
                search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS knowledge_facts_search_idx "
            "ON knowledge_facts USING GIN (search_vector)"
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS fact_evidence (
                fact_id TEXT NOT NULL REFERENCES knowledge_facts(fact_id) ON DELETE CASCADE,
                source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id),
                locator TEXT NOT NULL,
                evidence_text TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (fact_id, source_id, locator)
            )
            """
        )
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                chunk_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id),
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                page_number INTEGER,
                embedding vector({self._dimensions}) NOT NULL,
                search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS knowledge_chunks_search_idx "
            "ON knowledge_chunks USING GIN (search_vector)"
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_sections (
                section_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id),
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                page_start INTEGER NOT NULL CHECK (page_start > 0),
                page_end INTEGER NOT NULL CHECK (page_end >= page_start),
                UNIQUE (source_id, code)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_pages (
                source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id),
                page_number INTEGER NOT NULL CHECK (page_number > 0),
                section_id TEXT REFERENCES knowledge_sections(section_id),
                content_hash TEXT NOT NULL,
                extracted_text TEXT NOT NULL DEFAULT '',
                review_status TEXT NOT NULL DEFAULT 'pending',
                reviewed_at DATE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_id, page_number)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tariff_entries (
                tariff_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id),
                section_id TEXT NOT NULL REFERENCES knowledge_sections(section_id),
                page_number INTEGER NOT NULL,
                category TEXT NOT NULL,
                service_code TEXT NOT NULL DEFAULT '',
                service_name TEXT NOT NULL,
                delivery_channel TEXT NOT NULL DEFAULT '',
                statement_code TEXT NOT NULL DEFAULT '',
                value_type TEXT NOT NULL,
                amount NUMERIC(16, 4),
                minimum_amount NUMERIC(16, 4),
                maximum_amount NUMERIC(16, 4),
                percentage_min NUMERIC(10, 6),
                percentage_max NUMERIC(10, 6),
                currency CHAR(3) NOT NULL DEFAULT 'BRL',
                billing_unit TEXT NOT NULL DEFAULT '',
                charging_event TEXT NOT NULL DEFAULT '',
                dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
                effective_from DATE NOT NULL,
                status TEXT NOT NULL DEFAULT 'review_required',
                confidence NUMERIC(5, 4),
                reviewed_at DATE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id, page_number)
                    REFERENCES knowledge_pages(source_id, page_number),
                CHECK (status <> 'published' OR reviewed_at IS NOT NULL)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS tariff_entries_lookup_idx "
            "ON tariff_entries (status, category, service_name, delivery_channel, effective_from DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS tariff_entries_dimensions_idx "
            "ON tariff_entries USING GIN (dimensions)"
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tariff_rules (
                rule_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id),
                page_number INTEGER NOT NULL,
                rule_code TEXT NOT NULL,
                text TEXT NOT NULL,
                effective_from DATE NOT NULL,
                status TEXT NOT NULL DEFAULT 'review_required',
                reviewed_at DATE,
                UNIQUE (source_id, rule_code, effective_from),
                FOREIGN KEY (source_id, page_number)
                    REFERENCES knowledge_pages(source_id, page_number),
                CHECK (status <> 'published' OR reviewed_at IS NOT NULL)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tariff_entry_rules (
                tariff_id TEXT NOT NULL REFERENCES tariff_entries(tariff_id) ON DELETE CASCADE,
                rule_id TEXT NOT NULL REFERENCES tariff_rules(rule_id),
                PRIMARY KEY (tariff_id, rule_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS service_packages (
                package_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id),
                section_id TEXT NOT NULL REFERENCES knowledge_sections(section_id),
                page_number INTEGER NOT NULL,
                name TEXT NOT NULL,
                audience TEXT NOT NULL DEFAULT 'pessoa_fisica',
                monthly_fee NUMERIC(16, 4),
                total_services_value NUMERIC(16, 4),
                dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
                effective_from DATE NOT NULL,
                status TEXT NOT NULL DEFAULT 'review_required',
                reviewed_at DATE,
                FOREIGN KEY (source_id, page_number)
                    REFERENCES knowledge_pages(source_id, page_number),
                CHECK (status <> 'published' OR reviewed_at IS NOT NULL)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS package_items (
                package_id TEXT NOT NULL REFERENCES service_packages(package_id) ON DELETE CASCADE,
                item_id TEXT NOT NULL,
                service_name TEXT NOT NULL,
                included_quantity NUMERIC(12, 2),
                item_value NUMERIC(16, 4),
                conditions JSONB NOT NULL DEFAULT '{}'::jsonb,
                PRIMARY KEY (package_id, item_id)
            )
            """
        )

    def _document_values(self, document: KnowledgeDocument) -> tuple:
        return (
            document.knowledge_id,
            document.title,
            document.source,
            document.text,
            document.product,
            document.topic,
            document.audience,
            document.version,
            document.status,
            document.reviewed_at,
            document.limitations,
        )

    def _row_to_document(self, row: tuple) -> KnowledgeDocument:
        return KnowledgeDocument(
            knowledge_id=row[0], title=row[1], source=row[2], text=row[3], product=row[4],
            topic=row[5], audience=row[6], version=row[7], status=row[8], reviewed_at=row[9],
            limitations=row[10],
        )

    def _vector_literal(self, vector: list[float]) -> str:
        return json.dumps(vector, separators=(",", ":"))

    def _stable_id(self, prefix: str, value: str) -> str:
        return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"

    def _page_number(self, title: str) -> int | None:
        match = re.search(r"pagina (\d+)", title, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _evidence_locator(self, text: str) -> str:
        match = re.search(r"pagina\s+(\d+)", text, flags=re.IGNORECASE)
        return f"page:{match.group(1)}" if match else "curated-snapshot"
