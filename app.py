import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from config import FILIAIS_DISPONIVEIS, PERIODOS_DISPONIVEIS

BASE_DIR = Path(__file__).resolve().parent
JOBS_DIR = BASE_DIR / "jobs"
FRONTEND_DIR = BASE_DIR / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR))

job_lock = threading.Lock()
active_job_id = None


def get_job_dir(job_id):
    return JOBS_DIR / job_id


def read_status(job_id):
    status_path = get_job_dir(job_id) / "status.json"
    if not status_path.exists():
        return None
    with open(status_path, encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/config")
def api_config():
    return jsonify(
        {
            "periodos": PERIODOS_DISPONIVEIS,
            "filiais": FILIAIS_DISPONIVEIS,
        }
    )


@app.route("/api/jobs", methods=["POST"])
def create_job():
    global active_job_id

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    filial = (data.get("filial") or "").strip()
    periodos = data.get("periodos") or []

    if not username or not password:
        return jsonify({"error": "Usuário e senha são obrigatórios."}), 400

    if not filial:
        return jsonify({"error": "Selecione uma filial."}), 400

    valid_periodos = [p for p in periodos if p in PERIODOS_DISPONIVEIS]
    if not valid_periodos:
        return jsonify({"error": "Selecione ao menos um período."}), 400

    with job_lock:
        if active_job_id:
            status = read_status(active_job_id)
            if status and status.get("status") in {"pending", "running"}:
                return jsonify(
                    {
                        "error": "Já existe uma extração em andamento. Aguarde a conclusão.",
                        "active_job_id": active_job_id,
                    }
                ), 409

        job_id = str(uuid.uuid4())
        job_dir = get_job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)

        status_path = job_dir / "status.json"
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "status": "pending",
                    "message": "Na fila para iniciar...",
                    "current": 0,
                    "total": len(valid_periodos),
                    "files": [],
                    "error": None,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        env = os.environ.copy()
        env["ZUORA_USER"] = username
        env["ZUORA_PASS"] = password
        env["FILIAL"] = filial
        env["JOB_DIR"] = str(job_dir)
        env["PERIODOS_JSON"] = json.dumps(valid_periodos)

        subprocess.Popen(
            [sys.executable, str(BASE_DIR / "extrair_arquivos_car.py")],
            env=env,
            cwd=str(BASE_DIR),
        )

        active_job_id = job_id

    return jsonify({"job_id": job_id})


@app.route("/api/jobs/<job_id>/status")
def job_status(job_id):
    job_dir = get_job_dir(job_id)
    if not job_dir.exists():
        return jsonify({"error": "Job não encontrado."}), 404

    status = read_status(job_id)
    if not status:
        return jsonify({"error": "Status indisponível."}), 404

    return jsonify(status)


@app.route("/api/jobs/<job_id>/files")
def job_files(job_id):
    job_dir = get_job_dir(job_id)
    if not job_dir.exists():
        return jsonify({"error": "Job não encontrado."}), 404

    files = sorted(
        f.name
        for f in job_dir.iterdir()
        if f.is_file() and f.suffix.lower() == ".csv"
    )
    return jsonify({"files": files})


@app.route("/api/jobs/<job_id>/download/<path:filename>")
def download_file(job_id, filename):
    job_dir = get_job_dir(job_id)
    file_path = job_dir / filename

    if not file_path.exists() or not file_path.is_file():
        return jsonify({"error": "Arquivo não encontrado."}), 404

    if file_path.suffix.lower() != ".csv":
        return jsonify({"error": "Tipo de arquivo inválido."}), 400

    return send_from_directory(job_dir, filename, as_attachment=True)


@app.route("/api/jobs/active")
def active_job():
    global active_job_id

    if not active_job_id:
        return jsonify({"active": False})

    status = read_status(active_job_id)
    if not status:
        return jsonify({"active": False})

    if status.get("status") in {"done", "error"}:
        return jsonify({"active": False, "last_job_id": active_job_id, "status": status})

    return jsonify({"active": True, "job_id": active_job_id, "status": status})


if __name__ == "__main__":
    JOBS_DIR.mkdir(exist_ok=True)
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "4000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)
