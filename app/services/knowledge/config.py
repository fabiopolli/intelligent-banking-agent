from __future__ import annotations

from pathlib import Path

from app.services.knowledge.schemas import KnowledgeDocument


TARIFF_PDF_PATH = Path(".docs/tabela_geral_de_tarifas_pf_pdf.pdf")
TARIFF_PDF_SOURCE = ".docs/tabela_geral_de_tarifas_pf_pdf.pdf"
HELP_CENTER_SOURCE = "https://www.itau.com.br/atendimento-itau/para-voce"
POLICIES_SOURCE = "https://www.itau.com.br/relacoes-com-investidores/politicas/"

OFFICIAL_KNOWLEDGE_DOCUMENTS = [
    KnowledgeDocument(
        title="Atendimento Itau - canais digitais",
        source=HELP_CENTER_SOURCE,
        text=(
            "O atendimento Itau para clientes pessoa fisica concentra orientacoes de canais digitais, "
            "segunda via, ajuda com cartoes, seguranca, conta, pagamentos e suporte para uso do app."
        ),
    ),
    KnowledgeDocument(
        title="Tabela geral de tarifas PF",
        source=TARIFF_PDF_SOURCE,
        text=(
            "A tabela geral de tarifas pessoa fisica e a fonte oficial local para validar valores de "
            "tarifas, pacotes de servicos, segunda via, saques, transferencias, manutencao de conta e "
            "outros servicos bancarios sujeitos a cobranca."
        ),
    ),
    KnowledgeDocument(
        title="Politicas e relacoes com investidores Itau",
        source=POLICIES_SOURCE,
        text=(
            "As politicas publicadas pelo Itau reunem documentos institucionais de governanca, conduta, "
            "integridade, seguranca e relacionamento com partes interessadas."
        ),
    ),
]

DOCUMENTAL_QUERY_TERMS = {
    "acessos",
    "agencia",
    "app",
    "atendimento",
    "boleto",
    "boletos",
    "cartao",
    "cheque",
    "cheques",
    "chat",
    "comprovante",
    "comprovantes",
    "consignado",
    "conta",
    "corrente",
    "credito",
    "cambio",
    "cobranca",
    "desbloqueio",
    "duvidas",
    "fraude",
    "fraudes",
    "governanca",
    "itau",
    "itoken",
    "pacote",
    "aposentado",
    "aposentados",
    "pensionista",
    "pensionistas",
    "inss",
    "emprestimo",
    "juros",
    "investimento",
    "investimentos",
    "corretagem",
    "custodia",
    "fundo",
    "fundos",
    "tesouro",
    "taxa",
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
    "ted",
    "transferencia",
    "whatsapp",
}

TARIFF_QUERY_TERMS = {
    "anuidade",
    "cadastro",
    "cambio",
    "cobranca",
    "cartao",
    "cartoes",
    "cheque",
    "cheques",
    "deposito",
    "depositos",
    "emprestimo",
    "exportacao",
    "extrato",
    "extratos",
    "fundo",
    "fundos",
    "garantia",
    "importacao",
    "pacote",
    "poupanca",
    "saque",
    "segunda",
    "servico",
    "servicos",
    "tarifa",
    "tarifas",
    "ted",
    "transferencia",
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
