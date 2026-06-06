# app/core/helpers.py

import os
import json
import re
import unicodedata
import datetime
import pandas as pd

from app.globals import CONFIG_JOB_DIR

# ===== FUNZIONI DI NORMALIZZAZIONE =====

def normalize_emp_name(s: str) -> str:
    """Rimuove accenti, spazi e caratteri speciali per confrontare i nomi in modo sicuro."""
    if s is None or pd.isna(s): return ''
    s = str(s).lower().strip()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^a-z0-9]', '', s)
    return s

def _read_file_safe(file_path, header=0):
    """Legge file CSV o Excel in modo sicuro gestendo le diverse codifiche dei caratteri."""
    ext = file_path.suffix.lower()
    if ext == '.csv':
        try:
            return pd.read_csv(file_path, header=header, sep=None, engine='python', encoding='utf-8-sig')
        except:
            try:
                return pd.read_csv(file_path, header=header, sep=',', encoding='utf-8')
            except:
                return pd.read_csv(file_path, header=header, sep=';', encoding='latin1')
    else:
        return pd.read_excel(file_path, header=header, engine='openpyxl')

# ===== GESTIONE CONFIGURAZIONI JSON =====

def load_json_config(company_name: str, module: str = 'jobsistemi'):
    """Carica il file di configurazione dell'azienda dalla cartella di JOB Sistemi."""
    config_file = os.path.join(CONFIG_JOB_DIR, f'{company_name}.json')
    if not os.path.exists(config_file): return None
    with open(config_file, 'r', encoding='utf-8') as f: return json.load(f)

def get_effective_config(mode: str, company: str | None, module: str = 'jobsistemi'):
    """Restituisce direttamente la configurazione dell'azienda selezionata per JOB Sistemi."""
    if not company: raise ValueError("Azienda mancante")
    cfg = load_json_config(company, 'jobsistemi')
    if not cfg: raise ValueError(f'Configurazione "{company}" non trovata nel modulo JOB Sistemi')
    return cfg

# ===== UTILITÀ DI RICERCA COLONNE NELL'EXCEL =====

def normalize(s): 
    return str(s).strip() if s is not None else ''

def find_column_index(header_row, target_label: str):
    """Trova l'indice di una colonna basandosi sul nome esatto."""
    if target_label is None: return None
    target = normalize(target_label).lower()
    if target == '': return None
    for idx, val in enumerate(header_row):
        if pd.isna(val): continue
        if normalize(val).lower() == target: return idx
    return None

def find_column_index_contains(header_row, needle: str):
    """Trova l'indice di una colonna controllando se contiene una determinata parola chiave."""
    if not needle: return None
    needle = needle.lower()
    for idx, val in enumerate(header_row):
        if pd.isna(val): continue
        v = normalize(val).lower()
        if needle in v: return idx
    return None

# ===== MOTORE DI CALCOLO ORARIO MATEMATICO =====

def ore_to_decimal(val):
    """Converte formati orari stringa (es. 8,5 o 8:30 o 8h 30m) in valori decimali (float)."""
    if pd.isna(val) or val == '': return 0.0
    s = str(val).strip()
    if ',' in s:
        try: return round(float(s.replace(',', '.')), 2)
        except: return 0.0
    try: return round(float(s), 2)
    except: pass
    if ':' in s:
        try:
            parts = s.split(':')
            return round(int(parts[0]) + (int(parts[1]) / 60), 2)
        except: return 0.0
    if 'h' in s.lower():
        try:
            ore_match = re.search(r'(\d+)h', s)
            ore = int(ore_match.group(1)) if ore_match else 0
            if 'm' in s.lower():
                minuti_match = re.search(r'(\d+)m', s)
                minuti = int(minuti_match.group(1)) if minuti_match else 0
                return round(ore + (minuti / 60), 2)
            return float(ore)
        except: return 0.0
    return 0.0

def get_holiday_code(dettagli_val):
    """Identifica se la descrizione corrisponde a una festività nazionale fissa o mobile."""
    if pd.isna(dettagli_val) or dettagli_val == '': return None
    dettagli_str = str(dettagli_val).strip().lower()
    festivita = [
        'capodanno', 'epifania', 'pasqua', 'pasquetta', 's. giorgio', 
        'festa della liberazione', 'festa dei lavoratori', 'festa della repubblica', 
        'ferragosto', 'tutti i santi', 'immacolata concezione', 'natale', 'santo stefano'
    ]
    for f in festivita:
        if f in dettagli_str: return 'FES'
    return None

def get_giustificativo_code(dettagli_val, custom_mapping=None):
    """Associa la descrizione dell'evento (es. Ferie) al codice Job Sistemi configurato."""
    if pd.isna(dettagli_val) or dettagli_val == '': return None
    dettagli_str = str(dettagli_val).strip().lower()
    if custom_mapping:
        for key in sorted(custom_mapping.keys(), key=len, reverse=True):
            if key.lower() in dettagli_str:
                val = custom_mapping[key]
                if isinstance(val, dict):
                    return val.get('code', '')
                return val
    
    # Fallback standard se non mappato esplicitamente
    giustificativi = {
        'ferie': 'FE', 'altro': 'AL', 'malattia': 'MA', 'lutto': 'LUT', 
        'congedo parentale': 'CP', 'compensazione dei straordinari': 'CS', 
        'permessi non retribuiti': 'PR', 'rol': 'ROL', 'trasferta': 'TS', 
        'donazione di sangue': 'DS', 'permesso studio': 'PS', 'recupero compensativo': 'RC'
    }
    for key, code in giustificativi.items():
        if key in dettagli_str: return code
    return None

def extract_giustificativo_hours(dettagli_val):
    """Estrae le ore scritte tra parentesi o esplicitamente nel testo del giustificativo."""
    if pd.isna(dettagli_val) or dettagli_val == '': return 0.0
    s = str(dettagli_val).strip()
    m1 = re.search(r'\((\d+)h\s*(\d+)m\)', s)
    if m1: return round(int(m1.group(1)) + (int(m1.group(2)) / 60), 2)
    m2 = re.search(r'\((\d+)h\)', s)
    if m2: return float(m2.group(1))
    m3 = re.search(r'\((\d+)\)$', s)
    if m3: return round(int(m3.group(1)) / 60, 2)
    m4 = re.search(r'\((\d+):(\d+)\)', s)
    if m4: return round(int(m4.group(1)) + (int(m4.group(2)) / 60), 2)
    m5 = re.search(r'(\d+)h\s*(\d+)m', s)
    if m5: return round(int(m5.group(1)) + (int(m5.group(2)) / 60), 2)
    m6 = re.search(r'(\d+)h', s)
    if m6: return float(m6.group(1))
    m7 = re.search(r'\((\d+(?:\.\d+)?)\)', s)
    if m7: return float(m7.group(1))
    return 0.0

def calculate_hours_from_orario(orario_val) -> float:
    """Calcola la durata totale di un turno espresso come intervallo (es. 09:00 - 18:00) sottraendo 1h di pausa."""
    if pd.isna(orario_val) or orario_val == '': return 0.0
    s = str(orario_val).strip()
    m = re.search(r'(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})', s)
    if m:
        h_start, m_start, h_end, m_end = map(int, m.groups())
        start_dec = h_start + m_start / 60.0
        end_dec = h_end + m_end / 60.0
        if end_dec < start_dec:
            end_dec += 24.0
        diff = end_dec - start_dec
        if diff > 1.0:
            return round(diff - 1.0, 2) 
        return round(diff, 2)
    return 0.0

def find_folder_by_name(folder_name):
    """Cerca la cartella dei file sui percorsi di sistema comuni."""
    import platform
    from pathlib import Path
    home = Path.home()
    search_paths = [home / "Desktop", home / "Documents", home / "Downloads"]
    if platform.system() == 'Windows': search_paths.append(Path("C:\\"))
    else: search_paths.append(home)
    for path in search_paths:
        if path.exists():
            for item in path.iterdir():
                if item.is_dir() and item.name == folder_name: return str(item)
    return None

def fmt_hours(ore: float) -> str:
    """Formatta un valore decimale di ore in stringa HH:MM leggibile."""
    if ore is None or ore != ore:  # None o NaN
        return "0:00"
    ore_int = int(ore)
    min_int = int(round((ore - ore_int) * 60))
    return f"{ore_int}:{min_int:02d}"
