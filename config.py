"""Configurações compartilhadas entre Flask e o scraper."""

PERIODOS_DISPONIVEIS = {
    "Relatório 1": ["11/01/2022", "03/31/2023"],
    "Relatório 2": ["04/01/2023", "09/30/2023"],
    "Relatório 3": ["10/01/2023", "12/31/2023"],
    "Relatório 4": ["01/01/2024", "03/31/2024"],
    "Relatório 5": ["04/01/2024", "07/31/2024"],
    "Relatório 6": ["08/01/2024", "12/31/2024"],
    "Relatório 7": ["01/01/2025", "03/31/2025"],
    "Relatório 8": ["04/01/2025", "07/31/2025"],
    "Relatório 9": ["08/01/2025", "12/31/2025"],
    "Relatório 10": ["01/01/2026", "03/31/2026"],
    "Relatório 11": ["04/01/2026", "07/31/2026"],
}

FILIAIS_DISPONIVEIS = [
    {"label": "Rio de Janeiro - RJ (0009)", "value": "RIO DE JANEIRO|RJ|0009"},
]

NOME_RELATORIO = "Contas a Receber B2C Banco de Dados"

URL_LOGIN = "https://one.zuora.com/one-id/login"
URL_REPORTING = "https://eu.zuora.com/reporting/reportbuilder/reportingLanding.html"
URL_REPORT_RUNS = "https://eu.zuora.com/reporting/#/reportbuilder/report-management?tab=report-runs"

TIMEOUT_RENOMEAR = 300
