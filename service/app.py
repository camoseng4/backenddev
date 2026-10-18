"""Cloud Run IAM authenticates callers before this application is reached."""
import logging
from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from config import Settings
from snapshot_worker import process, validate_id


def create_app(*, processor=process, settings=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1024
    settings = settings or Settings.from_env()

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.post("/tasks/snapshot")
    def snapshot_task():
        if request.content_length is not None and request.content_length > 1024:
            return jsonify(status="invalid_request"), 413
        try:
            body = request.get_json()
            if type(body) is not dict or set(body) != {"organisation_id"}:
                raise ValueError("Expected only organisation_id")
            organisation_id = validate_id(body["organisation_id"])
        except (BadRequest, UnsupportedMediaType, ValueError):
            return jsonify(status="invalid_request"), 400
        try:
            outcome = processor(organisation_id, settings=settings)
            app.logger.info("snapshot_task organisation_id=%s outcome=%s", organisation_id, outcome.status)
            return jsonify(status=outcome.status), 503 if outcome.status == "busy" else 200
        except Exception:
            app.logger.exception("snapshot_task_failed organisation_id=%s", organisation_id)
            return jsonify(status="failed"), 503

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(status="invalid_request"), 413

    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
