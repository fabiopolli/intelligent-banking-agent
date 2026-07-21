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
                    INSERT INTO knowledge_documents (
                        knowledge_id, title, source, content, product, topic, audience,
                        version, status, reviewed_at, limitations, embedding
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (knowledge_id) DO UPDATE SET
                        title = EXCLUDED.title, source = EXCLUDED.source, content = EXCLUDED.content,
                        product = EXCLUDED.product, topic = EXCLUDED.topic, audience = EXCLUDED.audience,
                        version = EXCLUDED.version, status = EXCLUDED.status,
                        reviewed_at = EXCLUDED.reviewed_at, limitations = EXCLUDED.limitations,
                        embedding = EXCLUDED.embedding, updated_at = CURRENT_TIMESTAMP
                    """,
                    (*self._document_values(document), self._vector_literal(self._embedding.embed(document.text))),
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
                SELECT knowledge_id, title, source, content, product, topic, audience,
                       version, status, reviewed_at::text, limitations
                FROM knowledge_documents WHERE status = 'published' ORDER BY knowledge_id
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

    def search(self, query: str, top_k: int = 6) -> list[RetrievedKnowledge]:
        query_vector = self._vector_literal(self._embedding.embed(query))
        with self._connect() as connection, connection.cursor() as cursor:
            self._ensure_schema(cursor)
            cursor.execute(
                """
                WITH searchable AS (
                    SELECT title, source, content, search_vector, embedding
                    FROM knowledge_documents WHERE status = 'published'
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
            f"""
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                knowledge_id TEXT PRIMARY KEY,
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
            "CREATE INDEX IF NOT EXISTS knowledge_documents_search_idx "
            "ON knowledge_documents USING GIN (search_vector)"
        )
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
