from flask import Flask, request, jsonify
import os
import json
from datetime import datetime
import logging

app = Flask(__name__)

# ==============================
# CONFIGURAÇÃO
# ==============================
DB_FILE = "data.json"
API_TOKEN = os.getenv("API_TOKEN", "teste123")  # pega da variável de ambiente, default "teste123"

# Diretório e arquivo de logs
os.makedirs("logs", exist_ok=True)
log_path = os.path.join("logs", "app.log")
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def log_message(msg):
    logging.info(msg)

# ==============================
# FUNÇÕES DE LEITURA/ESCRITA
# ==============================
def load_data():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ==============================
# AUTENTICAÇÃO
# ==============================
def check_auth():
    auth_header = request.headers.get("Authorization", "")
    return auth_header == f"Bearer {API_TOKEN}"

# ==============================
# ROTAS
# ==============================
@app.route("/")
def home():
    return jsonify({
        "ok": True,
        "message": "API Database Controller está online.",
        "endpoints": ["/data (GET, POST, DELETE)", "/logs (GET)", "/debug-token (GET)"]
    })

@app.route("/data", methods=["GET", "POST", "DELETE"])
def handle_data():
    if not check_auth():
        return jsonify({"ok": False, "error": "Token inválido ou ausente."}), 401

    data = load_data()

    # ------------------------------
    # GET → retorna todos os registros
    # ------------------------------
    if request.method == "GET":
        log_message(f"[LIST] {len(data)} registros retornados.")
        return jsonify(data)

    # ------------------------------
    # POST → adiciona um novo registro
    # ------------------------------
    elif request.method == "POST":
        body = request.get_json(force=True)
        required_fields = ["url", "title", "filename"]
        if not all(field in body for field in required_fields):
            return jsonify({"ok": False, "error": "Campos ausentes."}), 400

        entry = {
            "url": body["url"],
            "title": body["title"],
            "filename": body["filename"],
            "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        data.append(entry)
        save_data(data)
        log_message(f"[ADD] {entry['title']} ({entry['filename']})")
        return jsonify({"ok": True, "message": "Adicionado com sucesso.", "entry": entry})

    # ------------------------------
    # DELETE → remove registro pelo filename
    # ------------------------------
    elif request.method == "DELETE":
        body = request.get_json(force=True)
        filename = body.get("filename")
        if not filename:
            return jsonify({"ok": False, "error": "Campo 'filename' é obrigatório."}), 400

        before = len(data)
        data = [item for item in data if item["filename"] != filename]
        after = len(data)
        save_data(data)

        if before == after:
            log_message(f"[DELETE] Tentativa de remover '{filename}', mas não encontrado.")
            return jsonify({"ok": False, "error": "Arquivo não encontrado."}), 404

        log_message(f"[DELETE] '{filename}' removido com sucesso.")
        return jsonify({"ok": True, "message": f"Removido '{filename}' com sucesso."})

# ------------------------------
# LOGS → retorna conteúdo do log
# ------------------------------
@app.route("/logs", methods=["GET"])
def get_logs():
    if not check_auth():
        return jsonify({"ok": False, "error": "Token inválido ou ausente."}), 401
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"logs": content.splitlines()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ------------------------------
# DEBUG → mostra qual token o Flask está lendo
# ------------------------------
@app.route("/debug-token", methods=["GET"])
def debug_token():
    return jsonify({
        "api_token_env": os.getenv("API_TOKEN"),
        "api_token_variable": API_TOKEN
    })

# ==============================
# MAIN
# ==============================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
