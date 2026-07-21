from __future__ import annotations

import re

from app.services.knowledge.config import TARIFF_PDF_SOURCE
from app.services.knowledge.schemas import KnowledgeDocument, RetrievedKnowledge, TariffGuidance
from app.services.knowledge.tariff_catalog import TariffCatalogLoader
from app.services.knowledge.tokenization import normalize_for_match, tokenize


class TariffAnswerBuilder:
    def __init__(self, documents: list[KnowledgeDocument], entries: list[dict] | None = None) -> None:
        self._documents = documents
        catalog = TariffCatalogLoader()
        self._entries = entries if entries is not None else catalog.load_entries()["entries"]
        auxiliary = catalog.load_auxiliary()
        self._packages = auxiliary["packages"]
        self._package_items = auxiliary["package_items"]

    def build(self, query: str, primary: RetrievedKnowledge) -> str:
        page_hint = self._extract_page_hint(primary.title)
        normalized_query = " ".join(tokenize(query))
        tariff_context = self._extract_tariff_context(normalized_query)
        subject = self._extract_subject(normalized_query)

        if self._has_blocked_conflict(normalized_query):
            return (
                "Não consigo confirmar o valor dessa tarifa com segurança neste momento. "
                "Para consultar o valor vigente, acesse 'tarifas e pacotes' no app Itaú "
                "ou fale com um especialista."
            )

        package_answer = self._find_package_answer(normalized_query)
        if package_answer is not None:
            return package_answer

        structured = self._find_structured_entries(normalized_query)
        if structured:
            return self._format_structured_answer(structured, normalized_query)

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

    def _find_package_answer(self, normalized_query: str) -> str | None:
        if "pacote essencial" not in normalized_query and "servicos essenciais" not in normalized_query:
            return None
        package = next(
            (
                item
                for item in self._packages
                if item["package_id"] == "package-servicos-essenciais"
                and item.get("status") == "published"
            ),
            None,
        )
        if package is None:
            return None

        items = [
            item
            for item in self._package_items
            if item["package_id"] == package["package_id"]
        ]
        rendered_items = [self._format_package_item(item) for item in items]
        monthly_fee = self._format_brl(package["monthly_fee"])
        fee_description = "não tem mensalidade" if float(package["monthly_fee"]) == 0 else f"custa {monthly_fee} por mês"
        included = "; ".join(rendered_items[:-1]) + f"; e {rendered_items[-1]}"
        return (
            f"O pacote de {package['name']} para conta corrente {fee_description}. "
            f"Ele inclui {included}. Serviços que excederem essas quantidades podem seguir a "
            "tarifa avulsa aplicável."
        )

    @staticmethod
    def _format_package_item(item: dict) -> str:
        quantity = item.get("included_quantity") or "quantidade não informada"
        service = item["service_name"].lower()
        if str(quantity) != "1":
            service = {
                "extrato mensal": "extratos mensais",
                "transferência entre contas itaú": "transferências entre contas Itaú",
            }.get(service, service)
        period = item.get("conditions", {}).get("period")
        suffix = " por mês" if period == "mensal" else (f" por {period}" if period else "")
        return f"{quantity} {service}{suffix}"

    def _find_structured_entries(self, normalized_query: str) -> list[dict]:
        intents = {
            "cartao_pre_pago": ("cartao pre pago", "pre pago"),
            "credito_imobiliario": ("credito imobiliario", "fgts", "imovel comercial", "sbpe"),
            "financiamento": ("financiamento", "leasing", "veiculo"),
            "consorcio": ("consorcio", "cota cedida"),
            "previdencia": ("previdencia",),
            "seguros": ("seguro de vida", "sobrevivencia"),
            "servicos_financeiros": ("escrow",),
            "conta_pagamento": ("conta de pagamento", "conta 100 digital"),
            "saque": ("saque", "retirada"),
            "ted": ("ted",),
            "extratos": ("extrato", "extratos"),
            "cheques": ("cheque", "cheques", "ccf", "sustacao", "revogacao"),
            "depositos": ("deposito", "depositos"),
            "cadastro": ("cadastro",),
            "cartoes": ("cartao", "cartoes", "anuidade"),
            "investimentos": (
                "fundo", "fundos", "investimento", "investimentos", "custodia", "corretagem",
                "tesouro", "cripto", "b3",
            ),
            "ordem_pagamento": ("ordem de pagamento",),
            "transferencias": ("transferencia", "transferencias"),
            "cobranca": ("cobranca", "cobrancas", "boleto", "titulo", "protesto", "negativacao"),
            "credito": ("credito", "emprestimo", "garantia", "rural"),
            "cambio": ("cambio", "importacao", "exportacao", "ccme", "moeda estrangeira"),
        }
        selected_intent = next(
            (name for name, terms in intents.items() if any(term in normalized_query for term in terms)),
            None,
        )
        if selected_intent is None:
            return []

        entries = [entry for entry in self._entries if entry.get("status") == "published"]
        if selected_intent == "ted":
            entries = [entry for entry in entries if "ted" in normalize_for_match(entry["service_name"])]
        elif selected_intent == "ordem_pagamento":
            entries = [entry for entry in entries if entry["tariff_id"] == "tar-ordem-pagamento"]
        elif selected_intent == "transferencias":
            entries = [entry for entry in entries if entry["category"] == "transferencias"]
        elif selected_intent == "saque":
            entries = [entry for entry in entries if entry["category"] == "saque"]
        else:
            entries = [entry for entry in entries if entry["category"] == selected_intent]

        if selected_intent in {
            "cobranca", "credito", "cambio", "cheques", "cartoes", "cartao_pre_pago",
            "credito_imobiliario", "financiamento", "consorcio", "previdencia", "seguros",
            "servicos_financeiros", "conta_pagamento", "investimentos",
        }:
            query_stems = self._specific_stems(normalized_query, selected_intent)
            scores = [self._specificity_score(entry, query_stems) for entry in entries]
            if scores and max(scores) > 0:
                best = max(scores)
                entries = [entry for entry, score in zip(entries, scores, strict=True) if score == best]

        channel_terms = {
            "internet": ("internet", "app", "aplicativo"),
            "terminal": ("terminal", "caixa eletronico", "autoatendimento", "banco24horas"),
            "presencial": ("presencial", "agencia", "guiche", "pessoal"),
            "correspondente": ("correspondente",),
            "exterior": ("exterior",),
        }
        requested_channel = next(
            (name for name, terms in channel_terms.items() if any(term in normalized_query for term in terms)),
            None,
        )
        if requested_channel:
            filtered = [
                entry for entry in entries
                if requested_channel in normalize_for_match(entry.get("delivery_channel", ""))
                or (requested_channel == "internet" and "eletronicos" in normalize_for_match(entry.get("delivery_channel", "")))
            ]
            if filtered:
                entries = filtered
        elif selected_intent == "saque" and "conta corrente" in normalized_query:
            common_channels = ("presencial", "pessoal", "terminal", "correspondente")
            entries = [
                entry
                for entry in entries
                if any(
                    channel in normalize_for_match(entry.get("delivery_channel", ""))
                    for channel in common_channels
                )
                and "exterior" not in normalize_for_match(entry.get("delivery_channel", ""))
                and "pix" not in normalize_for_match(entry.get("service_name", ""))
            ]
        return entries[:6]

    def _specific_stems(self, text: str, intent: str) -> set[str]:
        ignored = {
            "qual", "quanto", "custa", "tarifa", "taxa", "servico", "servicos",
            "para", "pela", "pelo", "uma", "cobranca", "credito", "cambio",
            "cheque", "cheques", "cartao", "cartoes", intent,
        }
        return {token[:5] for token in tokenize(text) if token not in ignored and len(token) >= 3}

    def _specificity_score(self, entry: dict, query_stems: set[str]) -> int:
        searchable = " ".join(
            (entry.get("service_name", ""), entry.get("statement_code", ""), entry.get("charging_event", ""))
        )
        entry_stems = {token[:5] for token in tokenize(searchable) if len(token) >= 3}
        service_stems = {token[:5] for token in tokenize(entry.get("service_name", "")) if len(token) >= 3}
        return 10 * len(query_stems & entry_stems) - len(service_stems - query_stems)

    def _has_blocked_conflict(self, normalized_query: str) -> bool:
        blocked = [entry for entry in self._entries if entry.get("status") == "review_required"]
        published = [entry for entry in self._entries if entry.get("status") == "published"]
        query_stems = self._specific_stems(normalized_query, "")
        blocked_score = max((self._specificity_score(entry, query_stems) for entry in blocked), default=0)
        published_score = max((self._specificity_score(entry, query_stems) for entry in published), default=0)
        return blocked_score >= 10 and blocked_score > published_score

    def _format_structured_answer(self, entries: list[dict], normalized_query: str) -> str:
        descriptions = []
        for entry in entries:
            if entry["value_type"] == "fixed":
                value = self._format_money(entry["amount"], entry.get("currency", "BRL"))
            elif entry["value_type"] == "maximum":
                value = f"até {self._format_brl(entry['maximum_amount'])}"
            elif entry["value_type"] == "percentage_range":
                value = f"de {self._format_percent(entry['percentage_min'])} a {self._format_percent(entry['percentage_max'])}"
            elif entry["value_type"] == "percentage_maximum":
                value = f"até {self._format_percent(entry['percentage_max'])}"
            elif entry["value_type"] == "percentage_fixed":
                value = self._format_percent(entry["percentage_max"])
            elif entry["value_type"] == "amount_range":
                value = f"de {self._format_brl(entry['minimum_amount'])} a {self._format_brl(entry['maximum_amount'])}"
            elif entry["value_type"] == "exempt":
                value = "isento"
            elif entry["value_type"] == "negotiated":
                value = "conforme negociação"
            elif entry["value_type"] == "greater_of":
                value = (
                    f"{self._format_percent(entry['percentage_max'])} ou "
                    f"{self._format_brl(entry['minimum_amount'])}, o que for maior"
                )
            elif entry["value_type"] == "formula":
                value = self._format_formula(entry)
            else:
                continue
            channel = entry.get("delivery_channel", "").strip()
            label = f"{channel}: {value}" if channel else f"{entry['service_name']}: {value}"
            if entry.get("billing_unit"):
                label += f" ({entry['billing_unit']})"
            descriptions.append(label)
        if not descriptions:
            return "Nao encontrei um valor publicado para esse servico e canal."
        if entries[0]["category"] == "saque":
            subject = "Saques em conta corrente" if "conta corrente" in normalized_query else "Saques"
            message = f"{subject}: " + "; ".join(descriptions)
        else:
            message = "; ".join(descriptions)
            message = message[0].upper() + message[1:]
        if entries[0]["category"] == "saque" and "conta corrente" in normalized_query:
            return (
                message
                + ". A cobranca ocorre quando o saque excede a franquia do seu pacote. "
                "Consulte a quantidade disponivel em 'tarifas e pacotes' no app."
            )
        suffix = ". Valores avulsos podem nao ser cobrados quando o servico estiver incluido na sua franquia ou pacote."
        if entries[0]["category"] == "saque":
            suffix += (
                " A tarifa pode variar conforme sua franquia e o canal; Banco24Horas segue a regra "
                "do terminal. Consulte 'tarifas e pacotes' no app para confirmar o que esta incluido."
            )
        return message + suffix

    def _format_formula(self, entry: dict) -> str:
        dimensions = entry.get("dimensions", {})
        if entry.get("amount") and dimensions.get("additional_percentage_of_volume"):
            return (
                f"{self._format_brl(entry['amount'])} + "
                f"{dimensions['additional_percentage_of_volume']} do volume"
            )
        if dimensions.get("fixed_amount") is not None and entry.get("percentage_max") is not None:
            return (
                f"{self._format_percent(entry['percentage_max'])} + "
                f"{self._format_brl(dimensions['fixed_amount'])}"
            )
        if dimensions.get("fixed_option") and dimensions.get("regressive_option"):
            return f"{dimensions['fixed_option']} ou {dimensions['regressive_option']} regressivo"
        return "conforme fórmula oficial da operação"

    def _format_brl(self, value: str) -> str:
        number = float(value)
        return f"R$ {number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _format_money(self, value: str, currency: str) -> str:
        if currency == "USD":
            number = float(value)
            rendered = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"US$ {rendered}"
        return self._format_brl(value)

    def _format_percent(self, value: str) -> str:
        return f"{float(value):.2f}%".replace(".", ",")

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
                "Em conta corrente, o saque avulso custa R$ 6,50 no atendimento presencial ou no "
                "terminal de autoatendimento e R$ 2,25 em correspondente no pais. A cobranca ocorre "
                "quando o saque excede a franquia incluida no seu pacote. Voce pode consultar a "
                "quantidade disponivel em 'tarifas e pacotes' no app."
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
