# app.py — Database Controller (Flask + SQLAlchemy)
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import os
from datetime import datetime
import logging
import json

app = Flask(__name__)

# -----------------------
# CONFIG
# -----------------------
# Use DATABASE_URL if definido (Render), senão sqlite local
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Tokens
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "teste123")      # frontend / user
WORKER_TOKEN = os.getenv("WORKER_TOKEN", "worker123") # workers

# Logging
os.makedirs("logs", exist_ok=True)
log_path = os.path.join("logs", "app.log")
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def log_message(msg):
    app.logger.info(msg)
    # também grava no arquivo via logging.basicConfig

# -----------------------
# MODELS
# -----------------------
class Video(db.Model):
    __tablename__ = "videos"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    url = db.Column(db.Text, nullable=False)
    title = db.Column(db.String(512), nullable=False)
    filename = db.Column(db.String(512), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "filename": self.filename,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class Job(db.Model):
    __tablename__ = "jobs"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    queue = db.Column(db.String(128), nullable=False, default="solicitacao")
    owner = db.Column(db.String(256), nullable=True)
    payload = db.Column(db.JSON, nullable=False)   # ex: {"url":"...","title":"...","filename":"..."}
    status = db.Column(db.String(64), nullable=False, default="pending")  # pending, processing, completed, failed, cancelled
    progress = db.Column(db.Integer, nullable=False, default=0)
    result = db.Column(db.JSON, nullable=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_retries = db.Column(db.Integer, nullable=False, default=3)
    worker_id = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "queue": self.queue,
            "owner": self.owner,
            "payload": self.payload,
            "status": self.status,
            "progress": self.progress,
            "result": self.result,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "worker_id": self.worker_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

# Create tables automatically
with app.app_context():
    db.create_all()

# -----------------------
# AUTH DECORATORS
# -----------------------
from functools import wraps

def require_auth_frontend(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "")
        if token != f"Bearer {AUTH_TOKEN}":
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper

def require_auth_worker(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "")
        if token != f"Bearer {WORKER_TOKEN}":
            return jsonify({"error": "worker unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper

# -----------------------
# ROUTES
# -----------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "ok": True,
        "message": "Database Controller online.",
        "endpoints": [
            "/videos (GET, POST, DELETE)",
            "/jobs (POST, GET list)",
            "/jobs/<id> (GET)",
            "/jobs/claim (POST) [worker]",
            "/jobs/<id>/progress (POST) [worker]",
            "/jobs/<id>/complete (POST) [worker]",
            "/jobs/<id>/fail (POST) [worker]",
            "/logs (GET)",
            "/debug-token (GET)"
        ]
    })

# -----------------------
# Videos endpoints (compat com seu /data)
# -----------------------
@app.route("/videos", methods=["GET"])
@require_auth_frontend
def list_videos():
    vids = Video.query.order_by(Video.created_at.desc()).all()
    return jsonify([v.to_dict() for v in vids])

@app.route("/videos", methods=["POST"])
@require_auth_frontend
def add_video():
    body = request.get_json(force=True)
    if not body or not all(k in body for k in ("url", "title", "filename")):
        return jsonify({"error": "missing fields"}), 400
    # upsert by filename
    v = Video.query.filter_by(filename=body["filename"]).first()
    if v:
        v.url = body["url"]
        v.title = body["title"]
    else:
        v = Video(url=body["url"], title=body["title"], filename=body["filename"])
        db.session.add(v)
    db.session.commit()
    log_message(f"[VIDEO] add/upsert {body['filename']}")
    return jsonify({"ok": True, "entry": v.to_dict()})

@app.route("/videos", methods=["DELETE"])
@require_auth_frontend
def delete_video():
    body = request.get_json(force=True)
    filename = body.get("filename")
    if not filename:
        return jsonify({"error": "filename required"}), 400
    v = Video.query.filter_by(filename=filename).first()
    if not v:
        return jsonify({"error": "not found"}), 404
    db.session.delete(v)
    db.session.commit()
    log_message(f"[VIDEO] deleted {filename}")
    return jsonify({"ok": True, "message": f"deleted {filename}"})

# -----------------------
# Jobs endpoints
# -----------------------
@app.route("/jobs", methods=["POST"])
@require_auth_frontend
def create_job():
    body = request.get_json(force=True)
    if not body or "payload" not in body:
        return jsonify({"error": "payload required"}), 400
    queue = body.get("queue", "solicitacao")
    owner = body.get("owner")
    payload = body["payload"]
    max_retries = int(body.get("max_retries", 3))
    job = Job(queue=queue, owner=owner, payload=payload, max_retries=max_retries, status="pending")
    db.session.add(job)
    db.session.commit()
    log_message(f"[JOB] created id={job.id} queue={queue} owner={owner}")
    return jsonify({"ok": True, "id": job.id}), 201

@app.route("/jobs", methods=["GET"])
@require_auth_frontend
def list_jobs():
    queue = request.args.get("queue")
    owner = request.args.get("owner")
    status = request.args.get("status")
    q = Job.query
    if queue:
        q = q.filter_by(queue=queue)
    if owner:
        q = q.filter_by(owner=owner)
    if status:
        q = q.filter_by(status=status)
    jobs = q.order_by(Job.created_at.desc()).limit(200).all()
    return jsonify([j.to_dict() for j in jobs])

@app.route("/jobs/<int:job_id>", methods=["GET"])
@require_auth_frontend
def get_job(job_id):
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job.to_dict())

# Worker claim: atomically take a pending job for a queue
@app.route("/jobs/claim", methods=["POST"])
@require_auth_worker
def claim_job():
    body = request.get_json(force=True)
    queue = body.get("queue", "solicitacao")
    worker_id = body.get("worker_id", "worker-unknown")

    engine = db.get_engine()
    dialect = engine.dialect.name

    # If using Postgres, use SELECT FOR UPDATE SKIP LOCKED inside transaction
    if dialect in ("postgresql", "cockroachdb"):
        with engine.begin() as conn:
            row = conn.execute(
                text("""
                SELECT id FROM jobs
                WHERE queue = :queue AND status = 'pending'
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """), {"queue": queue}
            ).fetchone()
            if not row:
                return ("", 204)
            job_id = row[0]
            conn.execute(
                text("""
                UPDATE jobs SET status = 'processing', worker_id = :worker_id, attempts = attempts + 1, updated_at = now()
                WHERE id = :jid
                """), {"worker_id": worker_id, "jid": job_id}
            )
            # select updated row to return
            new_row = conn.execute(text("SELECT * FROM jobs WHERE id = :jid"), {"jid": job_id}).fetchone()
            # convert row to dict (SQLAlchemy rowproxy -> mapping)
            # We will load job via ORM for convenience
            job = Job.query.get(job_id)
            log_message(f"[JOB] claimed id={job_id} by {worker_id}")
            return jsonify(job.to_dict())
    else:
        # Fallback (SQLite or others) — not truly atomic but ok for local testing
        job = Job.query.filter_by(queue=queue, status="pending").order_by(Job.created_at.asc()).with_for_update(read=False).first()
        if not job:
            return ("", 204)
        job.status = "processing"
        job.worker_id = worker_id
        job.attempts = job.attempts + 1
        job.updated_at = datetime.utcnow()
        db.session.commit()
        log_message(f"[JOB] claimed id={job.id} by {worker_id} (fallback)")
        return jsonify(job.to_dict())

@app.route("/jobs/<int:job_id>/progress", methods=["POST"])
@require_auth_worker
def job_progress(job_id):
    body = request.get_json(force=True)
    progress = body.get("progress")
    message = body.get("message")
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    if progress is not None:
        job.progress = int(progress)
    if message:
        existing = job.result or {}
        logs = existing.get("logs", [])
        logs.append({"ts": datetime.utcnow().isoformat(), "msg": message})
        existing["logs"] = logs
        job.result = existing
    job.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/jobs/<int:job_id>/complete", methods=["POST"])
@require_auth_worker
def job_complete(job_id):
    body = request.get_json(force=True)
    result = body.get("result", {})
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    job.status = "completed"
    job.progress = 100
    job.result = result
    job.updated_at = datetime.utcnow()
    db.session.commit()
    log_message(f"[JOB] completed id={job_id}")
    return jsonify({"ok": True})

@app.route("/jobs/<int:job_id>/fail", methods=["POST"])
@require_auth_worker
def job_fail(job_id):
    body = request.get_json(force=True)
    error = body.get("error", "unknown error")
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    job.status = "failed"
    job.result = {"error": error}
    job.updated_at = datetime.utcnow()
    db.session.commit()
    log_message(f"[JOB] failed id={job_id}: {error}")
    return jsonify({"ok": True})

# -----------------------
# Logs endpoint
# -----------------------
@app.route("/logs", methods=["GET"])
@require_auth_frontend
def get_logs():
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"logs": content.splitlines()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Debug token route
@app.route("/debug-token", methods=["GET"])
def debug_token():
    return jsonify({"auth_token_env": os.getenv("AUTH_TOKEN"), "auth_token_variable": AUTH_TOKEN,
                    "worker_token_env": os.getenv("WORKER_TOKEN"), "worker_token_variable": WORKER_TOKEN,
                    "database_url": (os.getenv('DATABASE_URL') or 'sqlite_local')})

# -----------------------
# MAIN
# -----------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
