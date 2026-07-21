from __future__ import annotations

import re

from app.services.knowledge.config import TARIFF_PDF_SOURCE
from app.services.knowledge.schemas import KnowledgeDocument, RetrievedKnowledge, TariffGuidance
from app.services.knowledge.tokenization import normalize_for_match, tokenize


class TariffAnswerBuilder:
    def __init__(self, documents: list[KnowledgeDocument]) -> None:
        self._documents = documents

    def build(self, query: str, primary: RetrievedKnowledge) -> str:
        page_hint = self._extract_page_hint(primary.title)
        normalized_query = " ".join(tokenize(query))
        tariff_context = self._extract_tariff_context(normalized_query)
        subject = self._extract_subject(normalized_query)

        if subject == "pacotes e servicos":
            return (
                "Posso informar tarifas e pacotes por aqui. Tambem posso te ajudar por aqui: diga o servico e o canal usados, "
                "como saque, segunda via, transferencia, conta poupanca ou pacote de servicos."
            )

        if tariff_context is not None:
            guidance = self._find_tariff_guidance(subject, tariff_context)
            if guidance is not None:
                return guidance.message

            return (
                f"Para {subject} em {tariff_context}, o valor depende do seu pacote, "
                "do canal usado e do tipo de conta. Voce pode conferir o valor pelo app em "
                "'tarifas e pacotes', ou continuar por aqui me dizendo se quer consultar pacote "
                "essencial, pacote contratado ou uso avulso do servico."
            )

        return (
            f"Para {subject}, a tarifa pode variar conforme pacote, canal e tipo de conta. "
            "Para eu te orientar melhor no chat, me diga o contexto: conta corrente, poupanca, "
            "terminal Itau, Banco24Horas ou outro canal."
        )

    def _extract_subject(self, normalized_query: str) -> str:
        if "saque" in normalized_query:
            return "saques"
        if "segunda" in normalized_query:
            return "segunda via e servicos relacionados"
        if "pacote" in normalized_query or "servicos" in normalized_query:
            return "pacotes e servicos"
        if "poupanca" in normalized_query:
            return "conta poupanca"
        return "tarifas e servicos bancarios"

    def _extract_tariff_context(self, normalized_query: str) -> str | None:
        if "conta corrente" in normalized_query:
            return "conta corrente"
        if "conta poupanca" in normalized_query or "poupanca" in normalized_query:
            return "conta poupanca"
        if "banco24horas" in normalized_query or "24horas" in normalized_query:
            return "Banco24Horas"
        if "terminal itau" in normalized_query or "caixa eletronico" in normalized_query:
            return "terminal Itau"
        return None

    def _find_tariff_guidance(self, subject: str, tariff_context: str) -> TariffGuidance | None:
        if subject != "saques":
            return None

        if tariff_context == "terminal Itau":
            return TariffGuidance(
                page_hint="pagina 7",
                message=(
                    "O saque em terminal de autoatendimento custa R$ 6,50 quando excede a "
                    "quantidade gratuita ou incluida no pacote. Em contas exclusivamente "
                    "eletronicas, essa tarifa nao pode ser cobrada nesse canal."
                ),
            )
        if tariff_context == "Banco24Horas":
            return TariffGuidance(
                page_hint="pagina 7",
                message=(
                    "Para saque em correspondente no pais, a tarifa avulsa indicada e R$ 2,25. "
                    "No Banco24Horas, a cobranca depende da franquia do pacote; diga qual e o seu "
                    "pacote para eu confirmar a regra aplicavel."
                ),
            )
        if tariff_context != "conta corrente":
            return None

        return TariffGuidance(
            page_hint="pagina 7",
            message=(
                "Para saque em conta corrente, a tarifa avulsa e R$ 6,50 no atendimento presencial "
                "ou terminal de autoatendimento, e R$ 2,25 em correspondente no pais. Os primeiros saques "
                "previstos na quantidade mensal "
                "do seu pacote podem ser feitos em qualquer canal. Depois dessa franquia, os saques seguintes "
                "devem seguir os canais previstos, como caixas eletronicos e Banco24Horas. Pode haver "
                "tarifa avulsa se voce ultrapassar a quantidade incluida ou usar um canal fora das regras. "
                "Para validar sua franquia, consulte 'tarifas e pacotes' no app."
            ),
        )

    def _find_pdf_document_containing(self, phrases: list[str]) -> KnowledgeDocument | None:
        normalized_phrases = [normalize_for_match(phrase) for phrase in phrases]
        for document in self._documents:
            if document.source != TARIFF_PDF_SOURCE:
                continue
            normalized_text = normalize_for_match(document.text)
            if all(phrase in normalized_text for phrase in normalized_phrases):
                return document
        return None

    def _extract_page_hint(self, title: str) -> str:
        match = re.search(r"pagina (\d+)", title)
        if match is None:
            return ""
        return f", pagina {match.group(1)}"
