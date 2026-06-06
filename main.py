# main.py

from flask import request, jsonify, send_file, render_template
import os, json, io
from pathlib import Path

# Calcolo del percorso assoluto del server
BASE_DIR = Path(__file__).resolve().parent

# Inizializzazione dell'applicazione tramite la fabbrica pulita
from app import create_app
app = create_app()

app.template_folder = str(BASE_DIR / 'Templates')
app.static_folder = str(BASE_DIR / 'Static')

# Importazione degli helpers strettamente necessari
from app.core.helpers import get_effective_config, _read_file_safe
from app.modules.jobsistemi.logic import run_jobsistemi_conversion

# ===== ROTTA MULTI-TENANT DINAMICA =====
# Ogni cliente accede al proprio spazio isolato tramite un URL dedicato (es: /azienda/cliente_a)
@app.route('/azienda/<tenant_id>')
def index(tenant_id):
    # Verifichiamo preventivamente se esiste la configurazione per evitare accessi orfani
    cfg = load_tenant_config_internal(tenant_id)
    if not cfg:
        return f"❌ Errore Architetturale: Il tenant '{tenant_id}' non è censito a sistema.", 404
        
    # Serviamo l'interfaccia. Il frontend saprà chi è l'utente grazie all'URL
    return render_template('index.html')


# ===== API: CARICAMENTO DEI DATI CONFIGURAZIONE (ISOLATO) =====
@app.route('/api/job/config/<tenant_id>', methods=['GET'])
def get_tenant_config(tenant_id):
    cfg = load_tenant_config_internal(tenant_id)
    if not cfg:
        return jsonify({'success': False, 'message': 'Tenant non trovato'}), 404
    return jsonify({'success': True, 'config': cfg})


# ===== API: SALVATAGGIO CONFIGURAZIONE (PROTETTO DA TENANT_ID) =====
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


# ===== API SINCRENA: ELABORAZIONE FILE IN-MEMORY E RILASCIO TRACCIATO =====
@app.route('/api/start-conversion/<tenant_id>', methods=['POST'])
def start_conversion(tenant_id):
    try:
        # 1. Recupero dei file trasmessi in streaming multipart HTTP dal browser
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or len(uploaded_files) == 0 or uploaded_files[0].filename == '':
            return jsonify({'success': False, 'message': 'Nessun file selezionato o ricevuto dal server.'}), 400

        # 2. Parsing dei parametri booleani per le opzioni ore di JOB Sistemi
        job_dynamic_hours_ore = request.form.get('job_dynamic_hours_ore') == 'true'
        job_dynamic_hours_turni = request.form.get('job_dynamic_hours_turni') == 'true'

        # 3. Caricamento della configurazione del rispettivo tenant
        effective_config = load_tenant_config_internal(tenant_id)
        if not effective_config:
            return jsonify({'success': False, 'message': 'Impossibile mappare il tenant richiesto.'}), 404

        # Instanziamo una struttura in memoria che simuli i file fisici per non rompere la logica preesistente
        class InMemoryFile:
            def __init__(self, filename, stream):
                self.stem = Path(filename).stem
                self.suffix = Path(filename).suffix
                self._stream = stream
            
            def open_dataframe(self, header=0):
                # Leggiamo il dataframe direttamente dai byte in RAM
                self._stream.seek(0)
                if self.suffix.lower() == '.csv':
                    return pd.read_csv(self._stream, header=header, sep=None, engine='python', encoding='utf-8-sig')
                else:
                    return pd.read_excel(self._stream, header=header, engine='openpyxl')

        processed_mem_files = []
        for file in uploaded_files:
            # Leggiamo il file dentro un buffer di memoria RAM sicuro
            file_buffer = io.BytesIO(file.read())
            processed_mem_files.append(InMemoryFile(file.filename, file_buffer))

        # 4. Mock temporaneo di un task_id interno per retrocompatibilità con run_jobsistemi_conversion
        # Nota: Essendo sincrono, creiamo al volo lo stato nel dizionario e lo distruggiamo subito dopo
        from app.globals import conversion_tasks
        mock_task_id = "sync_web_task"
        conversion_tasks[mock_task_id] = {'message': 'Elaborazione in RAM...'}

        # Intercettiamo i metodi interni di helpers/logic che cercavano file sul disco, 
        # iniettando l'apertura in-memory personalizzata
        # Modifichiamo leggermente l'esecuzione logica per passargli la nostra astrazione in RAM
        res = run_jobsistemi_conversion_web_adapted(
            mock_task_id, processed_mem_files, effective_config, tenant_id, job_dynamic_hours_ore, job_dynamic_hours_turni
        )

        # Pulizia immediata della memoria task globale
        if mock_task_id in conversion_tasks:
            del conversion_tasks[mock_task_id]

        if not res or 'content' not in res:
            return jsonify({'success': False, 'message': 'Errore durante la generazione del tracciato logico.'}), 500

        # 5. RESTITUZIONE DIRETTA DEL FILE DI TESTO NELLA RISPOSTA HTTP
        # L'architettura è stateless: non scriviamo nulla su disco, rispondiamo direttamente con i dati calcolati
        return jsonify({
            'success': True,
            'fileName': f"tracciato_job_{tenant_id}.txt",
            'fileContent': res['content'],
            'stats': res['result_data']
        })

    except Exception as e:
        import traceback
        return jsonify({'success': False, 'message': f"Errore Cloud: {str(e)}", 'details': traceback.format_exc()}), 500


# ===== INTERFACCIA HELPER INTERNA DI BACKEND =====
def load_tenant_config_internal(tenant_id):
    """Funzione ingegneristica per caricare in modo sicuro la configurazione senza risalire i path."""
    from app.globals import CONFIG_JOB_DIR
    # Normalizzazione per evitare attacchi di Path Traversal (es: ../../)
    safe_tenant = os.path.basename(tenant_id)
    path = os.path.join(CONFIG_JOB_DIR, f'{safe_tenant}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_jobsistemi_conversion_web_adapted(task_id, mem_files, effective_config, company, job_dynamic_hours_ore, job_dynamic_hours_turni):
    """
    Adattatore Web ad alte prestazioni basato sulla tua vecchia funzione logic.py.
    Sostituisce la lettura da file fisico con la lettura atomica in RAM.
    """
    from app.core.helpers import normalize_emp_name, get_giustificativo_code, extract_giustificativo_hours, calculate_hours_from_orario, ore_to_decimal
    import re, datetime

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
            # Usiamo la nostra astrazione in RAM invece del vecchio metodo che cercava il percorso su disco
            df = f.open_dataframe(header=0)
            if len(df) <= 4: continue
            
            # Estrazione nome dipendente dal nome del file (es: Mario_Rossi_esportazione.xlsx -> Mario Rossi)
            name_raw = f.stem.split('_')[0].split('-')[0].title()
            norm_name = normalize_emp_name(name_raw)
            
            if norm_name not in norm_emp_map: continue
            orig_config_name, emp_code = norm_emp_map[norm_name]
            emp_code = str(emp_code).strip()
            if not emp_code or emp_code.lower() == 'nan': continue
            
            processed_emps += 1
            header_row = df.iloc[3]
            
            # Mappatura indici colonne
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
        'result_data': {
            'dipendenti': processed_emps, 
            'ore': round(total_ore_count, 2)
        }
    }