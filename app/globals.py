# app/globals.py

# ===== VARIABILI DI STATO CONDIVISE =====
# Tiene traccia dei task di conversione in background (progressi, messaggi, errori)
conversion_tasks = {} 

# Salva l'ultimo tracciato generato pronto per essere scaricato o salvato
last_conversion_data = None 

# ===== COSTANTI GLOBALI =====
# Manteniamo esclusivamente la cartella dedicata a JOB Sistemi
CONFIG_JOB_DIR = 'Configurazioni/Config_Job'

# ===== DIZIONARI E SET CONDIVISI =====
# Questa lista di giustificativi serve per i calcoli orari interni (es. ferie, malattie)
GIUSTIFICATIVI_PAGATI_DEFAULT = {'FE', 'AL', 'MA', 'LUT', 'CP', 'CS', 'ROL', 'TS', 'DS', 'PS', 'RC'} 

GIORNI_SETTIMANA_IT = {0: 'Lun', 1: 'Mar', 2: 'Mer', 3: 'Gio', 4: 'Ven', 5: 'Sab', 6: 'Dom'}

MESI_IT = {
    1: 'Gennaio', 2: 'Febbraio', 3: 'Marzo', 4: 'Aprile', 5: 'Maggio', 6: 'Giugno',
    7: 'Luglio', 8: 'Agosto', 9: 'Settembre', 10: 'Ottobre', 11: 'Novembre', 12: 'Dicembre'
}

# Colonne speciali usate dal motore di calcolo durante l'analisi dei file Excel
SPECIAL_COLUMNS_MONITOR = ['data', 'ore lavorate', 'orario di lavoro', 'totale ore', 'dettagli', 'ore', 'giustificativo']