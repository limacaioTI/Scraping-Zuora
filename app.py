from flask import Flask, send_from_directory, request
import os
import subprocess

app = Flask(__name__, static_folder='frontend')

# Rota para servir a página inicial
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# Rota que recebe os dados do formulário e roda o script
@app.route('/iniciar-scraping', methods=['POST'])
def iniciar():
    username = request.form['username']
    password = request.form['password']

    # Criamos um ambiente isolado para o processo
    env_customizado = os.environ.copy()
    env_customizado["SCRAPER_USER"] = username
    env_customizado["SCRAPER_PASS"] = password

    # Executa o seu scraper.py passando o ambiente com as credenciais
    subprocess.Popen(["python", "extrair_arquivos_car.py"], env=env_customizado)

    return "Scraping iniciado com sucesso! Verifique o terminal do servidor."

if __name__ == '__main__':
    app.run(debug=True, port=5000)