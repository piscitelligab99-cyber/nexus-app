# main.py

import sys, traceback

print("=== AVVIO MAIN.PY ===", flush=True)

try:
    from flask import request, jsonify, send_file, render_template
    import os, json, io
    import pandas as pd
    from pathlib import Path
    print("=== IMPORT BASE OK ===", flush=True)
except Exception as e:
    print("=== ERRORE IMPORT BASE ===", flush=True)
    traceback.print_exc()
    sys.exit(1)

try:
    BASE_DIR = Path(__file__).resolve().parent
    from app import create_app
    print("=== CREATE_APP OK ===", flush=True)
except Exception as e:
    print("=== ERRORE CREATE_APP ===", flush=True)
    traceback.print_exc()
    sys.exit(1)

try:
    app = create_app()
    app.template_folder = str(BASE_DIR / 'Templates')
    app.static_folder = str(BASE_DIR / 'Static')
    print("=== APP CREATA OK ===", flush=True)
except Exception as e:
    print("=== ERRORE INIT APP ===", flush=True)
    traceback.print_exc()
    sys.exit(1)

try:
    from app.core.helpers import get_effective_config, _read_file_safe
    from app.modules.jobsistemi.logic import run_jobsistemi_conversion
    print("=== IMPORT MODULI OK ===", flush=True)
except Exception as e:
    print("=== ERRORE IMPORT MODULI ===", flush=True)
    traceback.print_exc()
    sys.exit(1)

# ===== ROTTA MULTI-TENANT DINAMICA =====
@app.route('/azienda/<tenant_id>')
def index(tenant_id):
    cfg = load_tenant_config_internal(tenant_id)
    if not cfg:
        return f"❌ Errore Architetturale: Il tenant '{tenant_id}' non è censito a sistema.", 404
    return render_template('index.html')

@app.route('/api/job/config/<tenant_id>', methods=['GET'])
def get_tenant_config(tenant_id):
    cfg = load_tenant_config_internal(tenant_id)
    if not cfg:
        return jsonify({'success': False, 'message': 'Tenant non trovato'}), 404
    return jsonify({'success': True, 'config': cfg})

@app.route('/api/job/config/<tenant_id>', methods=['POST'])
def save_tenant_config(tenant_id):
    try:
        data = request.json
        if not data or 'config' not in data:
            return jsonify({'success': False, 'message': 'Dati non validi'}), 400
        from app.globals import CONFIG_JOB_DIR
        path = os.path.join(CONFIG_JOB_DIR, f'{tenant_id}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data['config'], f, indent=4)
        return jsonify({'success': True, 'message': 'Configurazione blindata e salvata!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Errore di scrittura: {str(e)}'}), 500

@app.route('/api/start-conversion/<tenant_id>', methods=['POST'])
def start_conversion(tenant_id):
    try:
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or len(uploaded_files) == 0 or uploaded_files[0].filename == '':
            return jsonify({'success': False, 'message': 'Nessun file selezionato o ricevuto dal server.'}), 400

        job_dynamic_hours_ore = request.form.get('job_dynamic_hours_ore') == 'true'
        job_dynamic_hours_turni = request.form.get('job_dynamic_hours_turni') == 'true'

        effective_config = load_tenant_config_internal(tenant_id)
        if not effective_config:
            return jsonify({'success': False, 'message': 'Impossibile mappare il tenant richiesto.'}), 404

        class InMemoryFile:
            def __init__(self, filename, stream):
                self.stem = Path(filename).stem
                self.suffix = Path(filename).suffix
                self._stream = stream
            
            def open_dataframe(self, header=0):
                self._stream.seek(0)
                if self.suffix.lower() == '.csv':
                    return pd.read_csv(self._stream, header=header, sep=None, engine='python', encoding='utf-8-sig')
                else:
                    return pd.read_excel(self._stream, header=header, engine='openpyxl')

        processed_mem_files = []
        for file in uploaded_files:
            file_buffer = io.BytesIO(file.read())
            processed_mem_files.append(InMemoryFile(file.filename, file_buffer))

        from app.globals import conversion_tasks
        mock_task_id = "sync_web_task"
        conversion_tasks[mock_task_id] = {'message': 'Elaborazione in RAM...'}

        res = run_jobsistemi_conversion_web_adapted(
            mock_task_id, processed_mem_files, effective_config, tenant_id, job_dynamic_hours_ore, job_dynamic_hours_turni
        )

        if mock_task_id in conversion_tasks:
            del conversion_tasks[mock_task_id]

        if not res or 'content' not in res:
            return jsonify({'success': False, 'message': 'Errore durante la generazione del tracciato logico.'}), 500

        return jsonify({
            'success': True,
            'fileName': f"tracciato_job_{tenant_id}.txt",
            'fileContent': res['content'],
            'stats': res['result_data']
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f"Errore Cloud: {str(e)}", 'details': traceback.format_exc()}), 500


def load_tenant_config_internal(tenant_id):
    from app.globals import CONFIG_JOB_DIR
    safe_tenant = os.path.basename(tenant_id)
    path = os.path.join(CONFIG_JOB_DIR, f'{safe_tenant}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_jobsistemi_conversion_web_adapted(task_id, mem_files, effective_config, company, job_dynamic_hours_ore, job_dynamic_hours_turni):
    from app.core.helpers import normalize_emp_name, get_giustificativo_code, extract_giustificativo_hours, calculate_hours_from_orario, ore_to_decimal
    import re

    lines = []
    comp_code = str(effective_config.get('company_code', '')).strip()
    emp_map = effective_config.get('employees', {})
    raw_causals_map = effective_config.get('causals', {})
    
    simple_causals_map = {}
    for k, v in raw_causals_map.items():
        if isinstance(v, dict): simple_causals_map[k] = v.get('code', '')
        else: simple_causals_map[k] = v

    norm_emp_map = {normalize_emp_name(k): (k, v) for k, v in emp_map.items()}
    total_ore_count = 0.0
    processed_emps = 0

    for f in mem_files:
        try:
            df = f.open_dataframe(header=0)
            if len(df) <= 4: continue
            
            name_raw = f.stem.split('_')[0].split('-')[0].title()
            norm_name = normalize_emp_name(name_raw)
            
            if norm_name not in norm_emp_map: continue
            orig_config_name, emp_code = norm_emp_map[norm_name]
            emp_code = str(emp_code).strip()
            if not emp_code or emp_code.lower() == 'nan': continue
            
            processed_emps += 1
            header_row = df.iloc[3]
            
            from app.core.helpers import find_column_index, find_column_index_contains
            idx_data = find_column_index(header_row, "Data") or find_column_index_contains(header_row, 'data')
            idx_ore = find_column_index(header_row, "Ore Lavorate") or find_column_index_contains(header_row, 'ore lavorate')
            idx_det = find_column_index(header_row, "Dettagli") or find_column_index_contains(header_row, 'dettagli')
            idx_orario = find_column_index(header_row, "Orario di lavoro") or find_column_index_contains(header_row, 'orario di lavoro')

            for r in range(4, len(df)):
                row_val = df.iloc[r]
                val_data = str(row_val[idx_data]).strip()
                match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', val_data)
                if not match: continue

                giorno_int, mese_int, anno_str_full = int(match.group(1)), int(match.group(2)), match.group(3)
                data_txt = f"{giorno_int:02d}{mese_int:02d}{anno_str_full[-2:]}"

                det_str = str(row_val[idx_det]).strip() if idx_det is not None else ""
                if not det_str or det_str.lower() == 'nan': continue
                
                giust_code = get_giustificativo_code(det_str, simple_causals_map)
                if not giust_code: continue

                causale_padded = giust_code.ljust(3)
                ore_dettaglio = extract_giustificativo_hours(det_str)
                
                if ore_dettaglio > 0:
                    ore_calc = ore_dettaglio
                else:
                    if (job_dynamic_hours_ore or job_dynamic_hours_turni) and idx_orario is not None:
                        val_orario_str = str(row_val[idx_orario]).strip()
                        ore_da_orario = 0.0
                        if job_dynamic_hours_turni and '-' in val_orario_str:
                            ore_da_orario = calculate_hours_from_orario(val_orario_str)
                        elif job_dynamic_hours_ore:
                            ore_da_orario = ore_to_decimal(val_orario_str)
                        
                        ore_lavorate_effettive = ore_to_decimal(row_val[idx_ore]) if idx_ore is not None else 0.0
                        ore_calc = max(0.0, round(ore_da_orario - ore_lavorate_effettive, 2))
                        if ore_calc == 0.0: ore_calc = ore_lavorate_effettive
                    else:
                        ore_calc = ore_to_decimal(row_val[idx_ore]) if idx_ore is not None else 0.0

                ore_int = int(ore_calc)
                min_int = int(round((ore_calc - ore_int) * 60))
                ore_str = f"{ore_int:02d}{min_int:02d}00"

                line = f"{comp_code}{emp_code}{data_txt}{causale_padded}{ore_str}"
                lines.append(line)
                total_ore_count += ore_calc
        except:
            continue

    return {
        'content': "\n".join(lines),
        'result_data': {'dipendenti': processed_emps, 'ore': round(total_ore_count, 2)}
    }

# ===== PORT BINDING =====
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
