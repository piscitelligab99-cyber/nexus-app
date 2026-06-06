# app/globals.py
import os

# ===== VARIABILI DI STATO CONDIVISE =====
# Tiene traccia dei task di conversione in background (progressi, messaggi, errori)
conversion_tasks = {} 
# Salva l'ultimo tracciato generato pronto per essere scaricato o salvato
last_conversion_data = None 

# ===== COSTANTI GLOBALI =====
# Su Render (e altri cloud) il filesystem è read-only tranne /tmp
CONFIG_JOB_DIR = os.environ.get('CONFIG_JOB_DIR', '/tmp/Configurazioni/Config_Job')

# ===== DIZIONARI E SET CONDIVISI =====
GIUSTIFICATIVI_PAGATI_DEFAULT = {'FE', 'AL', 'MA', 'LUT', 'CP', 'CS', 'ROL', 'TS', 'DS', 'PS', 'RC'} 
GIORNI_SETTIMANA_IT = {0: 'Lun', 1: 'Mar', 2: 'Mer', 3: 'Gio', 4: 'Ven', 5: 'Sab', 6: 'Dom'}
MESI_IT = {
    1: 'Gennaio', 2: 'Febbraio', 3: 'Marzo', 4: 'Aprile', 5: 'Maggio', 6: 'Giugno',
    7: 'Luglio', 8: 'Agosto', 9: 'Settembre', 10: 'Ottobre', 11: 'Novembre', 12: 'Dicembre'
}
SPECIAL_COLUMNS_MONITOR = ['data', 'ore lavorate', 'orario di lavoro', 'totale ore', 'dettagli', 'ore', 'giustificativo']
