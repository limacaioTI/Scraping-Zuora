import os
import glob
import time
import shutil
from selenium import webdriver
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from urllib.parse import urlparse, parse_qs
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ------------------------------------------------------------------
# CONFIGURAÇÃO
# ------------------------------------------------------------------

url_login = "https://one.zuora.com/one-id/login"
url_reporting = "https://eu.zuora.com/reporting/reportbuilder/reportingLanding.html"
url_report_runs = "https://eu.zuora.com/reporting/#/reportbuilder/report-management?tab=report-runs"

load_dotenv()

usuario = os.getenv("ZUORA_USER")
senha = os.getenv("ZUORA_PASS")

NOME_RELATORIO = "Contas a Receber B2C Banco de Dados"

# 👉 Pasta onde os arquivos finais serão salvos.
# Pode ser a mesma pasta de downloads do Chrome ou outra (ex: uma pasta do projeto).
PASTA_DESTINO = os.path.join(os.path.expanduser("~"), "Downloads")

# Pasta de downloads que o Chrome vai usar (normalmente a mesma).
PASTA_DOWNLOAD_CHROME = os.path.join(os.path.expanduser("~"), "Downloads")

# Timeout de segurança para a espera de cada arquivo (em segundos)
TIMEOUT_RENOMEAR = 300

# nome do relatório (dict key) -> [data_inicio, data_fim]
dict_datas = {
    "Relatório 1": ["11/01/2022", "03/31/2023"],
    "Relatório 2": ["04/01/2023", "09/30/2023"],
    # "Relatório 3": ["10/01/2023", "12/31/2023"],
    # "Relatório 4": ["01/01/2024", "03/31/2024"],
    # "Relatório 5": ["04/01/2024", "07/31/2024"],
    # "Relatório 6": ["08/01/2024", "12/31/2024"],
    # "Relatório 7": ["01/01/2025", "03/31/2025"],
    # "Relatório 8": ["04/01/2025", "07/31/2025"],
    # "Relatório 9": ["08/01/2025", "12/31/2025"],
    # "Relatório 10": ["01/01/2026", "03/31/2026"],
    # "Relatório 11": ["04/01/2026", "07/31/2026"],
}

FILIAL = "RIO DE JANEIRO|RJ|0009"

UF = FILIAL.split("|")[1]

jobs = []

# ------------------------------------------------------------------
# SETUP DO CHROME (com pasta de download configurada)
# ------------------------------------------------------------------

options = webdriver.ChromeOptions()

prefs = {
    "download.default_directory": PASTA_DOWNLOAD_CHROME,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
}

options.add_experimental_option("prefs", prefs)

navegador = webdriver.Chrome(options=options)
navegador.maximize_window()
navegador.get(url_login)

wait = WebDriverWait(navegador, 20)
wait_longo = WebDriverWait(navegador, 300)  # relatório pode demorar bastante


# ------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ------------------------------------------------------------------

def fazer_login():
    wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(usuario)
    navegador.find_element(By.ID, "current-password").send_keys(senha)
    navegador.find_element(By.CSS_SELECTOR, ".css-1h2aaek").click()
    time.sleep(5)  # espera o redirecionamento pós-login


def navegar_ate_reporting():
    """Navega para a tela de Reporting e aguarda os painéis carregarem."""
    navegador.get(url_reporting)

    wait.until(
        EC.presence_of_all_elements_located(
            (By.XPATH, "//h4[contains(@class,'panel-title')]")
        )
    )

    time.sleep(1)


def abrir_report_runs():
    """Abre a tela Report Runs."""

    navegador.get(url_report_runs)

    wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".ui-grid-row"))
    )

    print("Report Runs aberto.")


def localizar_linha_run(run_id):

    try:
        link = navegador.find_element(
            By.XPATH,
            f"//a[contains(@href,'/export/{run_id}')]"
        )

        return link.find_element(
            By.XPATH,
            "./ancestor::div[contains(@class,'ui-grid-row')]"
        )

    except Exception:
        return None


def run_finalizado(linha):

    try:
        linha.find_element(
            By.XPATH,
            ".//*[contains(text(),'Completed')]"
        )

        return True

    except Exception:
        return False


def baixar_csv(run_id):
    """
    Abre a URL de export em nova aba para disparar o download.

    Importante: essa URL é uma resposta de download direto (não uma
    página navegável). Em muitas versões do Chrome, a aba nova se
    fecha SOZINHA assim que o download começa. Por isso:
      - guardamos o handle da janela principal ANTES de abrir a aba nova
      - checamos se a aba nova ainda existe antes de tentar fechá-la
      - voltamos para a janela principal pelo handle salvo, nunca por índice
    """

    janela_principal = navegador.current_window_handle
    handles_antes = set(navegador.window_handles)

    url = (
        "https://eu.zuora.com/reporting/"
        f"api/rest/v1/reportruns/reportbuilder/result/export/{run_id}"
    )

    navegador.execute_script(
        "window.open(arguments[0], '_blank');",
        url
    )

    # espera a nova aba de fato aparecer na lista de handles
    try:
        WebDriverWait(navegador, 10).until(
            lambda d: len(d.window_handles) > len(handles_antes)
        )
    except Exception:
        # se a aba nunca chegou a existir como handle separado
        # (pode acontecer se o download foi instantâneo), seguimos
        # em frente; o importante é garantir que voltamos pra principal
        pass

    novas_janelas = set(navegador.window_handles) - handles_antes

    if novas_janelas:
        nova_janela = novas_janelas.pop()

        # espera o Chrome iniciar o download
        time.sleep(5)

        # só tenta fechar se a aba ainda estiver aberta
        # (ela pode já ter se fechado sozinha após iniciar o download)
        if nova_janela in navegador.window_handles:
            try:
                navegador.switch_to.window(nova_janela)
                navegador.close()
            except Exception:
                pass
    else:
        # nenhuma aba nova detectada: o download provavelmente
        # já disparou e a aba fechou antes de conseguirmos capturá-la
        time.sleep(5)

    # volta pra janela principal pelo handle salvo (nunca por índice fixo,
    # já que a lista de handles pode ter mudado de ordem)
    navegador.switch_to.window(janela_principal)


def garantir_janela_ativa():
    """
    Garante que o driver está apontando para uma janela válida.
    Protege contra o caso em que uma aba se fechou sozinha (ex: download
    direto) e o Selenium ficou "sem janela ativa" (NoSuchWindowException).
    """
    try:
        # se isso não estourar exceção, já estamos numa janela válida
        navegador.current_window_handle
    except Exception:
        handles = navegador.window_handles
        if handles:
            navegador.switch_to.window(handles[0])
        else:
            raise RuntimeError(
                "Nenhuma janela do navegador está mais aberta. "
                "O Chrome pode ter travado ou sido fechado."
            )


def monitorar_downloads():

    abrir_report_runs()

    while True:

        todos = True

        for job in jobs:

            if job["baixado"]:
                continue

            linha = localizar_linha_run(job["run_id"])

            if linha is None:
                todos = False
                continue

            if not run_finalizado(linha):
                todos = False
                continue

            print(f"Baixando {job['nome_final']}")

            try:
                # timestamp capturado ANTES do clique, usado para filtrar
                # apenas arquivos criados a partir deste momento
                inicio_download = time.time()

                baixar_csv(job["run_id"])

                renomear_download(job, inicio_download)

                job["baixado"] = True

                print("Download concluído.\n")

            except Exception as e:
                # não deixa uma falha isolada derrubar o script inteiro;
                # o job simplesmente será tentado de novo no próximo loop
                print(f"  ❌ Falha ao baixar/renomear {job['nome_final']}: {e}")
                todos = False

            garantir_janela_ativa()
            navegador.get(url_report_runs)

            wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ui-grid-row"))
            )

        if todos:
            break

        print("Aguardando novos relatórios...")

        time.sleep(5)

        navegador.refresh()

        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ui-grid-row"))
        )


def renomear_download(job, inicio_download):
    """
    Aguarda o CSV baixado aparecer na pasta de download do Chrome e move
    para PASTA_DESTINO com o nome final do job.

    Só considera arquivos criados a partir de `inicio_download`, evitando
    pegar por engano um CSV antigo que já estivesse na pasta.
    """

    inicio_espera = time.time()

    while True:

        if time.time() - inicio_espera > TIMEOUT_RENOMEAR:
            raise TimeoutError(
                f"Timeout esperando o download de '{job['nome_final']}' "
                f"(> {TIMEOUT_RENOMEAR}s)."
            )

        # se existir .crdownload ainda está baixando
        if glob.glob(os.path.join(PASTA_DOWNLOAD_CHROME, "*.crdownload")):
            time.sleep(1)
            continue

        candidatos = glob.glob(
            os.path.join(
                PASTA_DOWNLOAD_CHROME,
                "InvoiceItem-Contas-a-Receber-B2C-Banco-de-Dados-Detail*.csv"
            )
        )

        # filtra só arquivos criados após o clique de download
        # (com 1s de folga para diferenças mínimas de precisão do relógio)
        arquivos = [
            arq for arq in candidatos
            if os.path.getctime(arq) >= inicio_download - 1
        ]

        if not arquivos:
            time.sleep(1)
            continue

        arquivo = max(arquivos, key=os.path.getctime)

        # garante que ninguém mais está escrevendo
        tamanho1 = os.path.getsize(arquivo)
        time.sleep(1)
        tamanho2 = os.path.getsize(arquivo)

        if tamanho1 != tamanho2:
            continue

        destino = os.path.join(PASTA_DESTINO, job["nome_final"])

        shutil.move(arquivo, destino)

        print(f"Arquivo salvo: {destino}")

        return


def abrir_modal_relatorio(nome_relatorio):
    """Abre o modal do relatório informado."""

    wait.until(
        EC.presence_of_all_elements_located(
            (By.XPATH, "//h4[contains(@class,'panel-title')]")
        )
    )

    paineis = navegador.find_elements(
        By.XPATH,
        "//h4[contains(@class,'panel-title')]"
    )

    print(f"Encontrados {len(paineis)} painéis de relatório.\n")

    painel_titulo = None
    texto = ""

    for painel in paineis:

        texto = painel.text
        texto = texto.replace("Run Detail Report", "")
        texto = " ".join(texto.split())

        print(f"• {texto}")

        if nome_relatorio.lower() in texto.lower():
            painel_titulo = painel
            break

    if painel_titulo is None:
        raise Exception(f"Relatório '{nome_relatorio}' não encontrado.")

    print(f"\nRelatório selecionado: {texto}")

    botao = painel_titulo.find_element(
        By.XPATH,
        ".//button[contains(@class,'buttonReport')]"
    )

    navegador.execute_script(
        "arguments[0].scrollIntoView({block:'center'});", botao
    )

    wait.until(lambda d: botao.is_displayed())

    try:
        botao.click()
    except Exception:
        navegador.execute_script("arguments[0].click();", botao)

    wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, "//*[contains(text(),'Edit Parameterize Filters')]")
        )
    )


def preencher_e_rodar(data_inicio_valor, data_fim_valor, filial=FILIAL):

    wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, "//*[contains(text(),'Edit Parameterize Filters')]")
        )
    )

    campo_from = wait.until(EC.visibility_of_element_located((By.NAME, "from")))
    campo_to = wait.until(EC.visibility_of_element_located((By.NAME, "to")))

    campo_branch = wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, "//td[contains(.,'Account: Branch')]/following-sibling::td//input")
        )
    )

    # FROM
    navegador.execute_script("arguments[0].value='';", campo_from)
    campo_from.send_keys(data_inicio_valor)
    campo_from.send_keys(Keys.TAB)

    # TO
    navegador.execute_script("arguments[0].value='';", campo_to)
    campo_to.send_keys(data_fim_valor)
    campo_to.send_keys(Keys.TAB)

    # BRANCH
    navegador.execute_script("arguments[0].value='';", campo_branch)
    campo_branch.send_keys(filial)
    campo_branch.send_keys(Keys.TAB)

    # RUN
    botao_run = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Run']"))
    )

    try:
        botao_run.click()
    except Exception:
        print("Clique normal falhou. Tentando JavaScript...")
        navegador.execute_script("arguments[0].click();", botao_run)

    wait.until(lambda d: "report-result" in d.current_url)

    url = navegador.current_url
    print(f"URL do resultado: {url}")

    fragment = urlparse(url).fragment
    query = fragment.split("?", 1)[1]
    params = parse_qs(query)
    report_run_id = params["reportRunId"][0]

    print(f"Run ID: {report_run_id}")

    return report_run_id


# ------------------------------------------------------------------
# EXECUÇÃO PRINCIPAL
# ------------------------------------------------------------------

fazer_login()
print("Login feito. URL:", navegador.current_url)

navegar_ate_reporting()
print("Chegou em Reporting. URL:", navegador.current_url)

for nome_relatorio, (data_inicio_valor, data_fim_valor) in dict_datas.items():
    try:
        print(f"Gerando: {nome_relatorio}")

        abrir_modal_relatorio(NOME_RELATORIO)
        print("  Modal aberto.")

        run_id = preencher_e_rodar(data_inicio_valor, data_fim_valor)

        jobs.append({
            "run_id": run_id,
            "report_id": NOME_RELATORIO,
            "inicio": data_inicio_valor,
            "fim": data_fim_valor,
            "uf": UF,
            "nome_final": (
                f"{len(jobs)+1}. "
                f"{data_inicio_valor.replace('/','')} ate "
                f"{data_fim_valor.replace('/','')} - {UF}.csv"
            ),
            "baixado": False,
        })

        print("Run enviado.")

        navegar_ate_reporting()

    except Exception as e:
        print(f"  ❌ Falha em {nome_relatorio}: {e}")
        continue

print()
print("Relatórios enviados:")
for job in jobs:
    print(job)

print()
print("Aguardando conclusão dos relatórios...")

monitorar_downloads()

print()
print("Todos os downloads concluídos.")