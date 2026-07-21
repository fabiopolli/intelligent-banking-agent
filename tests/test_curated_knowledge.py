from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services.knowledge.llm import (
    DockerModelRunnerGroundedFaqSynthesizer,
    OpenAIGroundedFaqSynthesizer,
    build_grounded_faq_synthesizer,
)
from app.services.knowledge.schemas import RetrievedKnowledge
from app.services.knowledge.catalog import CuratedCatalogLoader
from app.services.knowledge.embedding import DeterministicTokenEmbedding
from app.services.knowledge.retriever import LocalHybridRetriever
from app.services.knowledge.service import GroundedKnowledgeService
from frontend import ui_common
from frontend.ops_dashboard import latest_audit_events
from frontend.customer_chat import format_brl


def test_curated_catalog_has_unique_versioned_product_records() -> None:
    documents = CuratedCatalogLoader().load_documents()

    identifiers = [document.knowledge_id for document in documents]
    assert len(documents) >= 5
    assert len(identifiers) == len(set(identifiers))
    assert all(document.reviewed_at for document in documents)
    assert all(document.source for document in documents)
    assert {document.product for document in documents} >= {
        "tarifas",
        "conta_corrente",
        "credito_consignado_inss",
    }


def test_deterministic_embedding_is_stable_and_normalized() -> None:
    embedding = DeterministicTokenEmbedding(dimensions=64)

    first = embedding.embed("credito consignado para aposentados")
    second = embedding.embed("credito consignado para aposentados")

    assert first == second
    assert len(first) == 64
    assert abs(sum(value * value for value in first) - 1.0) < 1e-9


def test_curated_retrieval_prioritizes_consignado_inss() -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())

    result = retriever.retrieve("Qual a taxa do emprestimo consignado para aposentados?", top_k=2)

    assert result
    assert result[0].title == "Credito consignado INSS para aposentados e pensionistas"
    assert "itau.com.br" in result[0].source


def test_consignado_answer_is_grounded_and_does_not_invent_a_rate() -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    service = GroundedKnowledgeService(retriever=retriever, synthesizer=None)

    result = service.answer_with_trace("Qual a taxa do emprestimo consignado para aposentados?")

    assert "nao tem uma taxa unica" in result["message"].lower()
    assert "simulacao" in result["message"].lower()
    assert "%" not in result["message"]
    assert result["sources"] == [
        "https://www.itau.com.br/uniclass/emprestimos-financiamentos/emprestimo-consignado-inss"
    ]
    assert "controlled_consignado_answer_builder" in result["observability"]["tools_called"]


def test_knowledge_status_exposes_curated_catalog_metadata() -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    service = GroundedKnowledgeService(retriever=retriever, synthesizer=None)

    status = service.status()

    assert status["knowledge_store"] == "local"
    assert status["curated_document_count"] >= 5
    assert status["catalog_versions"] == [1]


def test_tariff_navigation_fast_path_does_not_call_llm() -> None:
    class FailingSynthesizer:
        provider_name = "must-not-run"

        def synthesize(self, query, contexts):  # noqa: ANN001, ANN201
            raise AssertionError("Stable tariff navigation must not call the LLM.")

    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    service = GroundedKnowledgeService(retriever=retriever, synthesizer=FailingSynthesizer())

    result = service.answer_with_trace("Onde consulto tarifas e pacotes de servicos?")

    assert "tarifas e pacotes" in result["message"].lower()
    assert "controlled_tariff_answer_builder" in result["observability"]["tools_called"]
    assert "grounded_faq_synthesizer" not in result["observability"]["tools_called"]


def test_tariff_answer_is_direct_and_includes_official_withdrawal_values() -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    service = GroundedKnowledgeService(retriever=retriever, synthesizer=None)

    result = service.answer_with_trace("Qual a tarifa de saque em conta corrente?")

    assert not result["message"].lower().startswith("claro")
    assert "R$ 6,50" in result["message"]
    assert "R$ 2,25" in result["message"]
    assert "Pix Saque" not in result["message"]
    assert "exterior" not in result["message"].lower()
    assert len(result["message"]) < 430
    assert result["message"].endswith("Posso ajudar com mais alguma dúvida?")
    assert result["sources"] == [".docs/tabela_geral_de_tarifas_pf_pdf.pdf"]


def test_customer_chat_formats_hitl_currency_in_pt_br() -> None:
    assert format_brl(15000) == "R$ 15.000,00"
    assert format_brl(6000.5) == "R$ 6.000,50"


def test_essential_services_package_uses_structured_official_composition() -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    service = GroundedKnowledgeService(retriever=retriever, synthesizer=None)

    result = service.answer_with_trace("Me fale sobre o pacote essencial para conta corrente")

    assert "não tem mensalidade" in result["message"]
    assert "10 folhas de cheque por mês" in result["message"]
    assert "4 saques" in result["message"]
    assert "2 extratos mensais" in result["message"]
    assert "2 transferências entre contas itaú" in result["message"].lower()
    assert "diga o servico e o canal" not in result["message"].lower()
    assert result["observability"]["llm"]["provider"] == "disabled"


def test_structured_ted_answer_is_direct_and_does_not_call_llm() -> None:
    class FailingSynthesizer:
        provider_name = "must-not-run"

        def synthesize(self, query, contexts):  # noqa: ANN001, ANN201
            raise AssertionError("Structured tariff query must not call the LLM.")

    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    service = GroundedKnowledgeService(retriever=retriever, synthesizer=FailingSynthesizer())

    result = service.answer_with_trace("Quanto custa uma TED pelo app?")

    assert "R$ 11,10" in result["message"]
    assert "controlled_tariff_answer_builder" in result["observability"]["tools_called"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Qual a anuidade do Itau Click Platinum?", "isento"),
        ("Qual a custodia B3 do Tesouro Direto?", "0,25%"),
        ("Quanto custa a implantacao de Escrow Account?", "R$ 20.000,00"),
        ("Qual a taxa de carregamento da previdencia?", "5,00%"),
        ("Quanto custa a cessao de direitos do consorcio?", "R$ 650,00"),
    ],
)
def test_structured_tariff_formats_all_official_value_types(query: str, expected: str) -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    result = GroundedKnowledgeService(retriever=retriever, synthesizer=None).answer_with_trace(query)

    assert expected in result["message"]
    assert result["observability"]["llm"]["provider"] == "disabled"


def test_conflicting_financing_values_are_not_published_to_customer() -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    result = GroundedKnowledgeService(retriever=retriever, synthesizer=None).answer_with_trace(
        "Qual a tarifa de cadastro para financiamento?"
    )

    assert "R$ 1.149,00" not in result["message"]
    assert "R$ 1.025,00" not in result["message"]
    assert "PDF" not in result["message"]
    assert "diverg" not in result["message"].lower()
    assert "Não consigo confirmar o valor" in result["message"]
    assert "app Itaú" in result["message"]
    assert result["message"].endswith("Posso ajudar com mais alguma dúvida?")
    assert "grounded_faq_synthesizer" not in result["observability"]["tools_called"]


def test_knowledge_follow_up_is_not_duplicated() -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    service = GroundedKnowledgeService(retriever=retriever, synthesizer=None)

    result = service.answer_with_trace("Qual a anuidade do Itau Click Platinum?")

    assert result["message"].count("Posso ajudar com mais alguma dúvida?") == 1


def test_exact_card_and_ccme_queries_do_not_return_neighboring_tariffs() -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    service = GroundedKnowledgeService(retriever=retriever, synthesizer=None)

    card = service.answer_with_trace("Qual a anuidade do Itau Click Platinum?")
    ccme = service.answer_with_trace("Quanto custa a ordem de pagamento recebida na CCME?")

    assert "isento" in card["message"]
    assert "R$ 214,80" not in card["message"]
    assert "US$ 20,00" in ccme["message"]


def test_structured_cheque_and_fund_answers_use_published_values() -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    service = GroundedKnowledgeService(retriever=retriever, synthesizer=None)

    cheque = service.answer_with_trace("Quanto custa uma folha de cheque?")
    funds = service.answer_with_trace("Qual a taxa de administracao de fundos de investimento?")

    assert "R$ 2,00" in cheque["message"]
    assert "0,10%" in funds["message"]
    assert "4,50%" in funds["message"]


def test_structured_credit_collection_and_fx_answers_are_direct() -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    service = GroundedKnowledgeService(retriever=retriever, synthesizer=None)

    collection = service.answer_with_trace("Qual a tarifa de cobranca sem registro?")
    credit = service.answer_with_trace("Quanto custa avaliar garantia de imovel para emprestimo?")
    fx = service.answer_with_trace("Quanto custa contratar cambio pela mesa?")

    assert "R$ 10,50" in collection["message"]
    assert "R$ 8,28" not in collection["message"]
    assert "R$ 3.420,00" in credit["message"]
    assert "R$ 59,90" not in credit["message"]
    assert "R$ 650,00" in fx["message"]
    assert "R$ 280,00" not in fx["message"]
    assert collection["observability"]["llm"]["provider"] == "disabled"
    assert credit["observability"]["llm"]["provider"] == "disabled"
    assert fx["observability"]["llm"]["provider"] == "disabled"


def test_investment_fees_answer_uses_curated_official_values() -> None:
    retriever = LocalHybridRetriever(documents=CuratedCatalogLoader().load_documents())
    service = GroundedKnowledgeService(retriever=retriever, synthesizer=None)

    result = service.answer_with_trace("Quais sao as taxas de investimentos e fundos?")

    assert "taxa zero de custodia" in result["message"].lower()
    assert "0,10% a 4,50%" in result["message"]
    assert "controlled_investment_answer_builder" in result["observability"]["tools_called"]
    assert "https://www.itau.com.br/investimentos" in result["sources"]
    assert ".docs/tabela_geral_de_tarifas_pf_pdf.pdf" in result["sources"]


def test_chat_client_timeout_exceeds_backend_llm_budget(monkeypatch) -> None:  # noqa: ANN001
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"message": "ok"}

    def fake_post(url, **kwargs):  # noqa: ANN001, ANN202
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(ui_common.httpx, "post", fake_post)

    ui_common.send_chat_message("http://api", "session", "123", "trusted-token", "tarifas")

    timeout = captured["timeout"]
    assert timeout.read == ui_common.CHAT_REQUEST_TIMEOUT_SECONDS
    assert timeout.connect == 3.0
    assert captured["headers"] == {"X-Demo-Auth-Token": "trusted-token"}
    assert "role" not in captured["json"]


def test_chat_client_turns_403_into_customer_safe_authorization_message(monkeypatch) -> None:  # noqa: ANN001
    class Response:
        status_code = 403

        def raise_for_status(self) -> None:
            raise AssertionError("403 should be handled before raising")

    monkeypatch.setattr(ui_common.httpx, "post", lambda *args, **kwargs: Response())

    result = ui_common.send_chat_message(
        "http://api",
        "authorization-session",
        "456",
        "customer-token",
        "Qual o saldo?",
    )

    assert result["route"] == "authorization_denied"
    assert "nao tem autorizacao" in result["message"].lower()
    assert "403" not in result["message"]
    assert result["observability"]["authorization"]["allowed"] is False


def test_dashboard_limits_visible_audit_to_three_latest_events() -> None:
    events = [{"event_id": str(index)} for index in range(1, 8)]

    visible = latest_audit_events(events)

    assert [event["event_id"] for event in visible] == ["7", "6", "5"]
    assert len(events) == 7


def test_docker_provider_disables_sdk_retries_and_falls_back(monkeypatch) -> None:  # noqa: ANN001
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            captured.update(kwargs)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._fail),
            )

        @staticmethod
        def _fail(**kwargs):  # noqa: ANN003, ANN205
            raise TimeoutError("provider timed out")

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    synthesizer = DockerModelRunnerGroundedFaqSynthesizer()
    context = [
        RetrievedKnowledge(
            title="Tarifas",
            source=".docs/tabela_geral_de_tarifas_pf_pdf.pdf",
            text="A tarifa de saque depende do pacote e do canal.",
            score=1.0,
        )
    ]

    message = synthesizer.synthesize("Tem tarifa para saque?", context)

    assert captured["timeout"] == settings.llm_timeout_seconds
    assert captured["max_retries"] == 0
    assert "tarifa de saque" in message.lower()
    assert synthesizer.last_trace["fallback_used"] is True
    assert synthesizer.last_trace["fallback_reason"] == "provider_error"
    assert synthesizer.last_trace["model"] == settings.docker_model_runner_model


def test_openai_provider_can_route_fallback_to_docker_model_runner(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "llm_grounded_faq_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_fallback_provider", "docker_model_runner")

    synthesizer = build_grounded_faq_synthesizer()

    assert isinstance(synthesizer, OpenAIGroundedFaqSynthesizer)
    assert isinstance(synthesizer._fallback, DockerModelRunnerGroundedFaqSynthesizer)  # noqa: SLF001
