# app/__init__.py

import os
import sys
import shutil
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS

from app.globals import CONFIG_JOB_DIR

# ===== CRASH LOGGING =====
def _write_crash_log(exc_type, exc, tb):
    try:
        with open("startup_error.log", "w", encoding="utf-8") as f:
            f.write("=== STARTUP ERROR ===\n")
            f.write("Python: " + sys.version + "\n")
            f.write("Executable: " + sys.executable + "\n\n")
            import traceback as _tb
            f.write("".join(_tb.format_exception(exc_type, exc, tb)))
    except:
        pass
sys.excepthook = _write_crash_log

def create_app():
    """Fabbrica dell'Applicazione: configura l'istanza di Flask per JOB Sistemi."""
    
    # 1. Copia le configurazioni dal repo verso /tmp al primo avvio
    src = Path(__file__).resolve().parent.parent / 'Configurazioni' / 'Config_Job'
    dst = Path(CONFIG_JOB_DIR)
    dst.mkdir(parents=True, exist_ok=True)
    if src.exists():
        for json_file in src.glob('*.json'):
            dest_file = dst / json_file.name
            if not dest_file.exists():
                shutil.copy2(json_file, dest_file)

    # 2. Inizializzazione Flask e CORS
    app = Flask(__name__)
    CORS(app)

    # Health check globale per il futuro monitoraggio sul server Cloud
    @app.route('/api/health', methods=['GET'])
    def health_check(): 
        return jsonify({'status': 'ok'})

    # 3. Registrazione dell'unico Blueprint rimasto (JOB Sistemi)
    from app.modules.jobsistemi.routes import jobsistemi_bp
    app.register_blueprint(jobsistemi_bp, url_prefix='/api/job')

    return app
