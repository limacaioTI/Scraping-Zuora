import glob
import json
import os
import shutil
import sys
import time
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import (
    NOME_RELATORIO,
    PERIODOS_DISPONIVEIS,
    TIMEOUT_RENOMEAR,
    URL_LOGIN,
    URL_REPORTING,
    URL_REPORT_RUNS,
)

load_dotenv()


def update_status(status_file, **kwargs):
    data = {}
    if os.path.exists(status_file):
        with open(status_file, encoding="utf-8") as f:
            data = json.load(f)
    data.update(kwargs)
    data["updated_at"] = time.time()
    os.makedirs(os.path.dirname(status_file), exist_ok=True)
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class ZuoraScraper:
    def __init__(
        self,
        usuario,
        senha,
        periodos,
        filial,
        pasta_destino,
        pasta_download,
        status_file,
    ):
        self.usuario = usuario
        self.senha = senha
        self.periodos = periodos
        self.filial = filial
        self.uf = filial.split("|")[1]
        self.pasta_destino = pasta_destino
        self.pasta_download = pasta_download
        self.status_file = status_file
        self.jobs = []
        self.navegador = None
        self.wait = None
        self.wait_longo = None

    def _set_progress(self, message, current=0, total=0, status="running", files=None, error=None):
        payload = {
            "status": status,
            "message": message,
            "current": current,
            "total": total,
        }
        if files is not None:
            payload["files"] = files
        if error is not None:
            payload["error"] = error
        update_status(self.status_file, **payload)

    def _setup_chrome(self):
        options = webdriver.ChromeOptions()
        prefs = {
            "download.default_directory": self.pasta_download,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
        }
        options.add_experimental_option("prefs", prefs)

        self.navegador = webdriver.Chrome(options=options)
        self.navegador.maximize_window()
        self.navegador.get(URL_LOGIN)
        self.wait = WebDriverWait(self.navegador, 20)
        self.wait_longo = WebDriverWait(self.navegador, 300)

    def _fazer_login(self):
        self._set_progress("Fazendo login no Zuora...")
        self.wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(
            self.usuario
        )
        self.navegador.find_element(By.ID, "current-password").send_keys(self.senha)
        self.navegador.find_element(By.CSS_SELECTOR, ".css-1h2aaek").click()
        time.sleep(5)

    def _navegar_ate_reporting(self):
        self.navegador.get(URL_REPORTING)
        self.wait.until(
            EC.presence_of_all_elements_located(
                (By.XPATH, "//h4[contains(@class,'panel-title')]")
            )
        )
        time.sleep(1)

    def _abrir_report_runs(self):
        self.navegador.get(URL_REPORT_RUNS)
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".ui-grid-row")))

    def _localizar_linha_run(self, run_id):
        try:
            link = self.navegador.find_element(
                By.XPATH,
                f"//a[contains(@href,'/export/{run_id}')]",
            )
            return link.find_element(
                By.XPATH,
                "./ancestor::div[contains(@class,'ui-grid-row')]",
            )
        except Exception:
            return None

    def _run_finalizado(self, linha):
        try:
            linha.find_element(By.XPATH, ".//*[contains(text(),'Completed')]")
            return True
        except Exception:
            return False

    def _baixar_csv(self, run_id):
        janela_principal = self.navegador.current_window_handle
        handles_antes = set(self.navegador.window_handles)

        url = (
            "https://eu.zuora.com/reporting/"
            f"api/rest/v1/reportruns/reportbuilder/result/export/{run_id}"
        )

        self.navegador.execute_script("window.open(arguments[0], '_blank');", url)

        try:
            WebDriverWait(self.navegador, 10).until(
                lambda d: len(d.window_handles) > len(handles_antes)
            )
        except Exception:
            pass

        novas_janelas = set(self.navegador.window_handles) - handles_antes

        if novas_janelas:
            nova_janela = novas_janelas.pop()
            time.sleep(5)
            if nova_janela in self.navegador.window_handles:
                try:
                    self.navegador.switch_to.window(nova_janela)
                    self.navegador.close()
                except Exception:
                    pass
        else:
            time.sleep(5)

        self.navegador.switch_to.window(janela_principal)

    def _garantir_janela_ativa(self):
        try:
            self.navegador.current_window_handle
        except Exception:
            handles = self.navegador.window_handles
            if handles:
                self.navegador.switch_to.window(handles[0])
            else:
                raise RuntimeError(
                    "Nenhuma janela do navegador está mais aberta. "
                    "O Chrome pode ter travado ou sido fechado."
                )

    def _renomear_download(self, job, inicio_download):
        inicio_espera = time.time()

        while True:
            if time.time() - inicio_espera > TIMEOUT_RENOMEAR:
                raise TimeoutError(
                    f"Timeout esperando o download de '{job['nome_final']}' "
                    f"(> {TIMEOUT_RENOMEAR}s)."
                )

            if glob.glob(os.path.join(self.pasta_download, "*.crdownload")):
                time.sleep(1)
                continue

            candidatos = glob.glob(
                os.path.join(
                    self.pasta_download,
                    "InvoiceItem-Contas-a-Receber-B2C-Banco-de-Dados-Detail*.csv",
                )
            )

            arquivos = [
                arq for arq in candidatos if os.path.getctime(arq) >= inicio_download - 1
            ]

            if not arquivos:
                time.sleep(1)
                continue

            arquivo = max(arquivos, key=os.path.getctime)

            tamanho1 = os.path.getsize(arquivo)
            time.sleep(1)
            tamanho2 = os.path.getsize(arquivo)

            if tamanho1 != tamanho2:
                continue

            destino = os.path.join(self.pasta_destino, job["nome_final"])
            shutil.move(arquivo, destino)
            return

    def _monitorar_downloads(self):
        self._abrir_report_runs()
        total = len(self.jobs)

        while True:
            todos = True

            for index, job in enumerate(self.jobs, start=1):
                if job["baixado"]:
                    continue

                linha = self._localizar_linha_run(job["run_id"])

                if linha is None:
                    todos = False
                    self._set_progress(
                        f"Aguardando relatório {index}/{total}: {job['nome_final']}",
                        current=index,
                        total=total,
                    )
                    continue

                if not self._run_finalizado(linha):
                    todos = False
                    self._set_progress(
                        f"Processando relatório {index}/{total}: {job['nome_final']}",
                        current=index,
                        total=total,
                    )
                    continue

                self._set_progress(
                    f"Baixando relatório {index}/{total}: {job['nome_final']}",
                    current=index,
                    total=total,
                )

                try:
                    inicio_download = time.time()
                    self._baixar_csv(job["run_id"])
                    self._renomear_download(job, inicio_download)
                    job["baixado"] = True
                except Exception as exc:
                    todos = False
                    raise RuntimeError(
                        f"Falha ao baixar {job['nome_final']}: {exc}"
                    ) from exc

                self._garantir_janela_ativa()
                self.navegador.get(URL_REPORT_RUNS)
                self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".ui-grid-row"))
                )

            if todos:
                break

            time.sleep(5)
            self.navegador.refresh()
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ui-grid-row"))
            )

    def _abrir_modal_relatorio(self, nome_relatorio):
        self.wait.until(
            EC.presence_of_all_elements_located(
                (By.XPATH, "//h4[contains(@class,'panel-title')]")
            )
        )

        paineis = self.navegador.find_elements(
            By.XPATH,
            "//h4[contains(@class,'panel-title')]",
        )

        painel_titulo = None
        texto = ""

        for painel in paineis:
            texto = painel.text
            texto = texto.replace("Run Detail Report", "")
            texto = " ".join(texto.split())

            if nome_relatorio.lower() in texto.lower():
                painel_titulo = painel
                break

        if painel_titulo is None:
            raise RuntimeError(f"Relatório '{nome_relatorio}' não encontrado.")

        botao = painel_titulo.find_element(
            By.XPATH,
            ".//button[contains(@class,'buttonReport')]",
        )

        self.navegador.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", botao
        )
        self.wait.until(lambda d: botao.is_displayed())

        try:
            botao.click()
        except Exception:
            self.navegador.execute_script("arguments[0].click();", botao)

        self.wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//*[contains(text(),'Edit Parameterize Filters')]")
            )
        )

    def _preencher_e_rodar(self, data_inicio_valor, data_fim_valor):
        self.wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//*[contains(text(),'Edit Parameterize Filters')]")
            )
        )

        campo_from = self.wait.until(EC.visibility_of_element_located((By.NAME, "from")))
        campo_to = self.wait.until(EC.visibility_of_element_located((By.NAME, "to")))
        campo_branch = self.wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//td[contains(.,'Account: Branch')]/following-sibling::td//input")
            )
        )

        self.navegador.execute_script("arguments[0].value='';", campo_from)
        campo_from.send_keys(data_inicio_valor)
        campo_from.send_keys(Keys.TAB)

        self.navegador.execute_script("arguments[0].value='';", campo_to)
        campo_to.send_keys(data_fim_valor)
        campo_to.send_keys(Keys.TAB)

        self.navegador.execute_script("arguments[0].value='';", campo_branch)
        campo_branch.send_keys(self.filial)
        campo_branch.send_keys(Keys.TAB)

        botao_run = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Run']"))
        )

        try:
            botao_run.click()
        except Exception:
            self.navegador.execute_script("arguments[0].click();", botao_run)

        self.wait.until(lambda d: "report-result" in d.current_url)

        url = self.navegador.current_url
        fragment = urlparse(url).fragment
        query = fragment.split("?", 1)[1]
        params = parse_qs(query)
        return params["reportRunId"][0]

    def run(self):
        total = len(self.periodos)
        if total == 0:
            raise ValueError("Nenhum período selecionado.")

        self._set_progress("Iniciando automação...", current=0, total=total, status="running")

        try:
            self._setup_chrome()
            self._fazer_login()
            self._navegar_ate_reporting()

            for index, (nome_relatorio, (data_inicio_valor, data_fim_valor)) in enumerate(
                self.periodos.items(), start=1
            ):
                self._set_progress(
                    f"Gerando {nome_relatorio} ({data_inicio_valor} a {data_fim_valor})",
                    current=index,
                    total=total,
                )

                self._abrir_modal_relatorio(NOME_RELATORIO)
                run_id = self._preencher_e_rodar(data_inicio_valor, data_fim_valor)

                self.jobs.append(
                    {
                        "run_id": run_id,
                        "report_id": NOME_RELATORIO,
                        "inicio": data_inicio_valor,
                        "fim": data_fim_valor,
                        "uf": self.uf,
                        "nome_final": (
                            f"{len(self.jobs) + 1}. "
                            f"{data_inicio_valor.replace('/', '')} ate "
                            f"{data_fim_valor.replace('/', '')} - {self.uf}.csv"
                        ),
                        "baixado": False,
                    }
                )

                self._navegar_ate_reporting()

            self._set_progress(
                "Aguardando conclusão dos relatórios no Zuora...",
                current=total,
                total=total,
            )
            self._monitorar_downloads()

            files = [job["nome_final"] for job in self.jobs]
            self._set_progress(
                "Extração concluída com sucesso.",
                current=total,
                total=total,
                status="done",
                files=files,
            )
        except Exception as exc:
            self._set_progress(
                str(exc),
                status="error",
                error=str(exc),
            )
            raise
        finally:
            if self.navegador:
                self.navegador.quit()


def parse_periodos(periodos_json):
    if not periodos_json:
        return {}

    nomes = json.loads(periodos_json)
    return {nome: PERIODOS_DISPONIVEIS[nome] for nome in nomes if nome in PERIODOS_DISPONIVEIS}


def main():
    usuario = os.getenv("ZUORA_USER")
    senha = os.getenv("ZUORA_PASS")
    filial = os.getenv("FILIAL", "RIO DE JANEIRO|RJ|0009")
    job_dir = os.getenv("JOB_DIR")
    periodos_json = os.getenv("PERIODOS_JSON", "[]")

    if not usuario or not senha:
        print("Erro: ZUORA_USER e ZUORA_PASS são obrigatórios.", file=sys.stderr)
        sys.exit(1)

    if not job_dir:
        print("Erro: JOB_DIR é obrigatório.", file=sys.stderr)
        sys.exit(1)

    periodos = parse_periodos(periodos_json)
    if not periodos:
        print("Erro: nenhum período válido selecionado.", file=sys.stderr)
        sys.exit(1)

    pasta_destino = job_dir
    pasta_download = os.path.join(job_dir, "_chrome_downloads")
    status_file = os.path.join(job_dir, "status.json")

    os.makedirs(pasta_destino, exist_ok=True)
    os.makedirs(pasta_download, exist_ok=True)

    update_status(
        status_file,
        status="running",
        message="Preparando automação...",
        current=0,
        total=len(periodos),
        files=[],
        error=None,
    )

    scraper = ZuoraScraper(
        usuario=usuario,
        senha=senha,
        periodos=periodos,
        filial=filial,
        pasta_destino=pasta_destino,
        pasta_download=pasta_download,
        status_file=status_file,
    )

    try:
        scraper.run()
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
