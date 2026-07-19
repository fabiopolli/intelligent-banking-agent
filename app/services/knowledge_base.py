from __future__ import annotations

import math
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.services.observability import traceable


@dataclass(frozen=True)
class KnowledgeDocument:
    title: str
    source: str
    text: str


@dataclass(frozen=True)
class RetrievedKnowledge:
    title: str
    source: str
    text: str
    score: float


OFFICIAL_KNOWLEDGE_DOCUMENTS = [
    KnowledgeDocument(
        title="Atendimento Itau - canais digitais",
        source="https://www.itau.com.br/atendimento-itau/para-voce",
        text=(
            "O atendimento Itau para clientes pessoa fisica concentra orientacoes de canais digitais, "
            "segunda via, ajuda com cartoes, seguranca, conta, pagamentos e suporte para uso do app."
        ),
    ),
    KnowledgeDocument(
        title="Tabela geral de tarifas PF",
        source=".docs/tabela_geral_de_tarifas_pf_pdf.pdf",
        text=(
            "A tabela geral de tarifas pessoa fisica e a fonte oficial local para validar valores de "
            "tarifas, pacotes de servicos, segunda via, saques, transferencias, manutencao de conta e "
            "outros servicos bancarios sujeitos a cobranca."
        ),
    ),
    KnowledgeDocument(
        title="Politicas e relacoes com investidores Itau",
        source="https://www.itau.com.br/relacoes-com-investidores/politicas/",
        text=(
            "As politicas publicadas pelo Itau reunem documentos institucionais de governanca, conduta, "
            "integridade, seguranca e relacionamento com partes interessadas."
        ),
    ),
]

TARIFF_PDF_PATH = Path(".docs/tabela_geral_de_tarifas_pf_pdf.pdf")
TARIFF_PDF_SOURCE = ".docs/tabela_geral_de_tarifas_pf_pdf.pdf"
HELP_CENTER_SOURCE = "https://www.itau.com.br/atendimento-itau/para-voce"
POLICIES_SOURCE = "https://www.itau.com.br/relacoes-com-investidores/politicas/"
DOCUMENTAL_QUERY_TERMS = {
    "acessos",
    "agencia",
    "app",
    "atendimento",
    "boleto",
    "boletos",
    "cartao",
    "chat",
    "comprovante",
    "comprovantes",
    "conta",
    "corrente",
    "desbloqueio",
    "duvidas",
    "fraude",
    "fraudes",
    "governanca",
    "itau",
    "itoken",
    "pacote",
    "pagamentos",
    "politica",
    "politicas",
    "poupanca",
    "renegociacao",
    "saque",
    "seguranca",
    "senha",
    "segunda",
    "servico",
    "servicos",
    "tarifa",
    "tarifas",
    "transferencia",
    "whatsapp",
}
RAG_STOPWORDS = {
    "aos",
    "com",
    "como",
    "das",
    "dos",
    "ita",
    "itau",
    "onde",
    "para",
    "pela",
    "pelo",
    "qual",
    "quais",
    "que",
    "seu",
    "sua",
    "voce",
}


class OfficialWebSnapshotIngestor:
    @traceable(name="Official Web Snapshot Ingestion", run_type="retriever")
    def load_documents(self) -> list[KnowledgeDocument]:
        return [
            KnowledgeDocument(
                title="Central de ajuda Itau - canais de atendimento",
                source=HELP_CENTER_SOURCE,
                text=(
                    "A Central de Ajuda Itau para voce apresenta atendimento pelo WhatsApp Itau, "
                    "consulta de saldos, limites, segunda via e duvidas. Tambem destaca o chat no app "
                    "ou internet para tirar duvidas e resolver o que precisar, alem de telefones e "
                    "encontre agencias."
                ),
            ),
            KnowledgeDocument(
                title="Central de ajuda Itau - topicos frequentes",
                source=HELP_CENTER_SOURCE,
                text=(
                    "Os topicos frequentes da Central de Ajuda incluem novo app Itau, dados cadastrais, "
                    "cartao de credito, conta corrente, tarifas, boletos, pagamentos e transferencias, "
                    "acessos, iToken, seguros, renegociacao, imposto de renda e investimentos."
                ),
            ),
            KnowledgeDocument(
                title="Central de ajuda Itau - seguranca e cartao",
                source=HELP_CENTER_SOURCE,
                text=(
                    "A Central de Ajuda orienta sobre desbloqueio de cartao, senha de acesso Itau, "
                    "seguranca e fraudes, contestacao de compras no cartao de credito e uso dos canais "
                    "digitais para atendimento seguro."
                ),
            ),
            KnowledgeDocument(
                title="Politicas Itau - governanca e integridade",
                source=POLICIES_SOURCE,
                text=(
                    "A pagina de politicas de relacoes com investidores do Itau concentra documentos "
                    "institucionais relacionados a governanca corporativa, integridade, etica, ESG, "
                    "informacoes ao mercado, resultados, relatorios e documentos regulatorios."
                ),
            ),
            KnowledgeDocument(
                title="Politicas Itau - mercado e regulatorio",
                source=POLICIES_SOURCE,
                text=(
                    "As politicas e documentos institucionais do Itau apoiam consultas sobre perfil "
                    "corporativo, governanca, ratings, renda fixa, documentos regulatorios, empresas do "
                    "grupo e comunicacao com investidores."
                ),
            ),
        ]


class TariffPdfIngestor:
    def __init__(
        self,
        pdf_path: Path = TARIFF_PDF_PATH,
        chunk_size: int = 900,
        chunk_overlap: int = 120,
        cache_path: Path = Path(".runtime/knowledge_tariff_chunks.json"),
    ) -> None:
        self._pdf_path = pdf_path
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._cache_path = cache_path

    @traceable(name="Tariff PDF Ingestion", run_type="retriever")
    def load_documents(self) -> list[KnowledgeDocument]:
        if not self._pdf_path.exists():
            return []

        cached = self._load_cache()
        if cached:
            return cached

        try:
            from pypdf import PdfReader
        except ImportError:
            return []

        reader = PdfReader(str(self._pdf_path))
        documents: list[KnowledgeDocument] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = self._normalize_whitespace(page.extract_text() or "")
            if not text:
                continue
            for chunk_index, chunk in enumerate(self._split_text(text), start=1):
                documents.append(
                    KnowledgeDocument(
                        title=f"Tabela geral de tarifas PF - pagina {page_number} - trecho {chunk_index}",
                        source=TARIFF_PDF_SOURCE,
                        text=f"Pagina {page_number}. {chunk}",
                    )
                )
        self._write_cache(documents)
        return documents

    def _load_cache(self) -> list[KnowledgeDocument]:
        if not self._cache_path.exists():
            return []

        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        if payload.get("pdf_signature") != self._pdf_signature():
            return []

        return [
            KnowledgeDocument(
                title=str(item["title"]),
                source=str(item["source"]),
                text=str(item["text"]),
            )
            for item in payload.get("documents", [])
        ]

    def _write_cache(self, documents: list[KnowledgeDocument]) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pdf_signature": self._pdf_signature(),
            "documents": [
                {
                    "title": document.title,
                    "source": document.source,
                    "text": document.text,
                }
                for document in documents
            ],
        }
        self._cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _pdf_signature(self) -> dict[str, int]:
        stat = self._pdf_path.stat()
        return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    def _split_text(self, text: str) -> list[str]:
        if len(text) <= self._chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self._chunk_size, len(text))
            chunks.append(text[start:end].strip())
            if end == len(text):
                break
            start = max(end - self._chunk_overlap, start + 1)
        return [chunk for chunk in chunks if chunk]

    def _normalize_whitespace(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()


def build_official_documents() -> list[KnowledgeDocument]:
    ingested = TariffPdfIngestor().load_documents()
    web_documents = OfficialWebSnapshotIngestor().load_documents()
    if not ingested:
        return OFFICIAL_KNOWLEDGE_DOCUMENTS + web_documents

    non_pdf_documents = [
        document
        for document in OFFICIAL_KNOWLEDGE_DOCUMENTS
        if document.source != TARIFF_PDF_SOURCE
    ]
    return non_pdf_documents + web_documents + ingested


class LocalHybridRetriever:
    def __init__(self, documents: list[KnowledgeDocument] | None = None) -> None:
        self._documents = documents or build_official_documents()
        self._tokenized_documents = [self._tokenize(document.text) for document in self._documents]
        self._document_frequency = self._build_document_frequency()

    @property
    def document_count(self) -> int:
        return len(self._documents)

    @property
    def sources(self) -> list[str]:
        return sorted({document.source for document in self._documents})

    def retrieve(self, query: str, top_k: int = 2) -> list[RetrievedKnowledge]:
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        ranked = [
            RetrievedKnowledge(
                title=document.title,
                source=document.source,
                text=document.text,
                score=self._score(query_terms, self._tokenized_documents[index], document.text),
            )
            for index, document in enumerate(self._documents)
        ]
        return [item for item in sorted(ranked, key=lambda item: item.score, reverse=True)[:top_k] if item.score > 0]

    def _score(self, query_terms: list[str], document_terms: list[str], document_text: str) -> float:
        lexical_score = self._bm25_like_score(query_terms, document_terms)
        semantic_score = self._semantic_overlap_score(query_terms, document_terms)
        phrase_bonus = self._phrase_bonus(query_terms, document_text)
        return lexical_score + semantic_score + phrase_bonus

    def _bm25_like_score(self, query_terms: list[str], document_terms: list[str]) -> float:
        score = 0.0
        document_length = max(len(document_terms), 1)
        average_length = max(
            sum(len(terms) for terms in self._tokenized_documents) / max(len(self._tokenized_documents), 1),
            1,
        )

        for term in set(query_terms):
            term_frequency = document_terms.count(term)
            if term_frequency == 0:
                continue
            inverse_document_frequency = math.log(
                1 + (len(self._documents) - self._document_frequency.get(term, 0) + 0.5)
                / (self._document_frequency.get(term, 0) + 0.5)
            )
            denominator = term_frequency + 1.2 * (1 - 0.75 + 0.75 * document_length / average_length)
            score += inverse_document_frequency * ((term_frequency * 2.2) / denominator)
        return score

    def _semantic_overlap_score(self, query_terms: list[str], document_terms: list[str]) -> float:
        query_set = set(query_terms)
        document_set = set(document_terms)
        if not query_set or not document_set:
            return 0.0
        return len(query_set & document_set) / len(query_set | document_set)

    def _phrase_bonus(self, query_terms: list[str], document_text: str) -> float:
        normalized_document = " ".join(self._tokenize(document_text))
        normalized_query = " ".join(query_terms)
        if normalized_query and normalized_query in normalized_document:
            return 1.0
        return 0.0

    def _build_document_frequency(self) -> dict[str, int]:
        frequency: dict[str, int] = {}
        for terms in self._tokenized_documents:
            for term in set(terms):
                frequency[term] = frequency.get(term, 0) + 1
        return frequency

    def _tokenize(self, text: str) -> list[str]:
        normalized = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")
        return [
            token
            for token in re.findall(r"[a-z0-9]+", normalized)
            if len(token) > 2 and token not in RAG_STOPWORDS
        ]


class GroundedKnowledgeService:
    def __init__(self, retriever: LocalHybridRetriever | None = None) -> None:
        self._retriever = retriever or LocalHybridRetriever()

    def answer(self, query: str) -> tuple[str, list[str]]:
        if not self._is_supported_documental_query(query):
            return (
                "Nao encontrei contexto oficial suficiente para responder com seguranca. "
                "Posso seguir por atendimento humano ou por uma fonte oficial mais especifica.",
                [],
            )

        retrieved = self._retriever.retrieve(query)
        if not retrieved or retrieved[0].score < 0.65:
            return (
                "Nao encontrei contexto oficial suficiente para responder com seguranca. "
                "Posso seguir por atendimento humano ou por uma fonte oficial mais especifica.",
                [],
            )

        primary = retrieved[0]
        excerpt = self._compact_excerpt(primary.text)
        if "tarifa" in query.lower() or "pacote" in query.lower():
            message = (
                "Para tarifas e pacotes, a resposta deve ser conferida na tabela geral de tarifas PF. "
                f"Encontrei contexto oficial no trecho: {excerpt}"
            )
        elif "politica" in query.lower() or "governanca" in query.lower():
            message = (
                "Para politicas institucionais, encontrei a fonte oficial de relacoes com investidores "
                f"e politicas do Itau. Trecho usado: {excerpt}"
            )
        else:
            message = (
                "Encontrei uma orientacao oficial de atendimento Itau relacionada a sua pergunta. "
                f"Trecho usado: {excerpt}"
            )

        sources = list(dict.fromkeys(item.source for item in retrieved))
        return message, sources

    def status(self) -> dict:
        return {
            "document_count": self._retriever.document_count,
            "sources": self._retriever.sources,
            "pdf_ingested": TARIFF_PDF_SOURCE in self._retriever.sources,
            "web_sources_loaded": all(
                source in self._retriever.sources
                for source in [HELP_CENTER_SOURCE, POLICIES_SOURCE]
            ),
        }

    def _compact_excerpt(self, text: str, limit: int = 220) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit].rstrip()}..."

    def _is_supported_documental_query(self, query: str) -> bool:
        query_terms = set(self._retriever._tokenize(query))
        return bool(query_terms & DOCUMENTAL_QUERY_TERMS)


knowledge_service = GroundedKnowledgeService()
