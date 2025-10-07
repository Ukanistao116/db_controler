from flask import Flask, request, jsonify
import os
import json
from datetime import datetime

app = Flask(__name__)

# Nome do arquivo JSON onde vamos salvar os dados
DB_FILE = "data.json"

# Token de autenticação
API_TOKEN = os.getenv("API_TOKEN", "teste123")

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

@app.route("/")
def home():
    return jsonify({
        "ok": True,
        "message": "API Database Controller está online.",
        "endpoints": ["/data (GET, POST, DELETE)"]
    })

@app.route("/data", methods=["GET", "POST", "DELETE"])
def handle_data():
    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {API_TOKEN}":
        return jsonify({"ok": False, "error": "Token inválido ou ausente."}), 401

    data = load_data()

    if request.method == "GET":
        return jsonify(data)

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
        return jsonify({"ok": True, "message": "Adicionado com sucesso.", "entry": entry})

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
            return jsonify({"ok": False, "error": "Arquivo não encontrado."}), 404
        return jsonify({"ok": True, "message": f"Removido '{filename}' com sucesso."})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
