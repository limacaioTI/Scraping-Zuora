# Extração Automática Zuora

Ferramenta interna para extrair relatórios "Contas a Receber B2C" do Zuora via navegador, com interface web simples para a equipe.

## Para quem usa (equipe não técnica)

1. Peça o link do app para quem mantém o servidor (ex.: `http://nome-do-pc:5000`).
2. Abra o link no navegador.
3. Informe usuário e senha do Zuora.
4. Escolha a filial e os períodos desejados.
5. Clique em **Iniciar extração**.
6. Acompanhe o progresso na tela e baixe os CSVs quando concluir.

Não é necessário instalar Python no seu computador.

## Para quem mantém o servidor (pessoa técnica)

### Pré-requisitos

- Python 3.10+
- Google Chrome instalado
- ChromeDriver compatível com a versão do Chrome (gerenciado automaticamente pelo Selenium 4.6+ na maioria dos casos)

### Instalação (uma vez)

```bash
cd Scraping-Zuora
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Subir o servidor

```bash
python app.py
```

O app ficará disponível em `http://0.0.0.0:5000` (acessível na rede local pelo IP da máquina).

Variáveis opcionais:

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `FLASK_HOST` | `0.0.0.0` | Interface de rede |
| `FLASK_PORT` | `5000` | Porta HTTP |
| `FLASK_DEBUG` | `false` | Modo debug (não usar em produção) |

### Uso via linha de comando (opcional)

Também é possível rodar o scraper diretamente:

```bash
export ZUORA_USER="seu_usuario"
export ZUORA_PASS="sua_senha"
export JOB_DIR="./jobs/manual"
export PERIODOS_JSON='["Relatório 1","Relatório 2"]'
export FILIAL="RIO DE JANEIRO|RJ|0009"
python extrair_arquivos_car.py
```

## Estrutura do projeto

```
Scraping-Zuora/
├── app.py                    # Servidor Flask + API de jobs
├── config.py                 # Períodos e filiais disponíveis
├── extrair_arquivos_car.py   # Automação Selenium
├── frontend/index.html       # Interface web
├── jobs/                     # Saída por execução (criada automaticamente)
└── requirements.txt
```

## API

| Rota | Método | Descrição |
|------|--------|-----------|
| `/` | GET | Interface web |
| `/api/config` | GET | Períodos e filiais |
| `/api/jobs` | POST | Inicia extração |
| `/api/jobs/<id>/status` | GET | Status em tempo real |
| `/api/jobs/<id>/files` | GET | Lista de CSVs |
| `/api/jobs/<id>/download/<arquivo>` | GET | Download do CSV |
| `/api/jobs/active` | GET | Job em andamento |

## Observações

- Apenas **uma extração por vez** é permitida (Selenium + Chrome na mesma máquina).
- Os arquivos ficam em `jobs/<job_id>/` no servidor; a interface oferece download pelo navegador.
- Use em rede interna ou VPN. Não exponha publicamente na internet sem HTTPS e autenticação.
- Credenciais do Zuora são passadas apenas para o processo do scraper e não são armazenadas em disco.
