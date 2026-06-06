# app/modules/jobsistemi/logic.py

import re
import datetime
import pandas as pd

from app.globals import conversion_tasks
from app.core.helpers import (
    _read_file_safe, normalize_emp_name, find_column_index, 
    find_column_index_contains, calculate_hours_from_orario, 
    ore_to_decimal, get_giustificativo_code, extract_giustificativo_hours, 
    fmt_hours
)

def run_jobsistemi_conversion(task_id, files, effective_config, company, folder_name, folder_path, job_dynamic_hours_ore, job_dynamic_hours_turni, fallback_schedules):
    conversion_tasks[task_id]['message'] = 'Generazione tracciato Job Sistemi...'
    lines = []
    comp_code = str(effective_config.get('company_code', '')).strip()
    emp_map = effective_config.get('employees', {})
    
    raw_causals_map = effective_config.get('causals', {})
    simple_causals_map = {}
    code_actions = {}
    
    for k, v in raw_causals_map.items():
        if isinstance(v, dict):
            c_code = v.get('code', '')
            simple_causals_map[k] = c_code
            code_actions[c_code] = v.get('festivity_action', 'ignora')
        else:
            simple_causals_map[k] = v
            code_actions[v] = 'ignora'

    norm_emp_map = {normalize_emp_name(k): (k, v) for k, v in emp_map.items()}

    # ----------------------------------------------------
    # ESTRAZIONE DATI DI RACCORDO NOMI E SCADENZARI
    # ----------------------------------------------------
    reconciliation_map = {}
    actual_schedules = {}
    if isinstance(fallback_schedules, dict):
        reconciliation_map = fallback_schedules.get('__reconciliation__', {})
        actual_schedules = {k: v for k, v in fallback_schedules.items() if k != '__reconciliation__'}
    else:
        actual_schedules = fallback_schedules

    # ----------------------------------------------------
    # CONTROLLO PRELIMINARE ACCOPPIAMENTO CARATTERI ACCENTATI
    # ----------------------------------------------------
    unreconciled_stems = set()
    for f in files:
        name_raw = f.stem.split('_')[0].title()
        
        effective_name = name_raw
        if name_raw in reconciliation_map:
            effective_name = reconciliation_map[name_raw]
            
        norm_name = normalize_emp_name(effective_name)
        if norm_name not in norm_emp_map:
            unreconciled_stems.add(name_raw)

    if unreconciled_stems:
        conversion_tasks[task_id].update({
            'status': 'needs_reconciliation',
            'progress': 100,
            'result': sorted(list(unreconciled_stems))
        })
        return None
    # ----------------------------------------------------

    total_ore_count = 0.0
    processed_emps = 0
    
    missing_employees_found = set()
    malformed_employees_found = set()
    missing_causals_found = set()
    zero_hours_found = [] 
    
    employees_needing_fallback = set()

    is_selene = (company and company.lower() == 'selene')
    is_quadrifoglio = (company and company.lower() == 'il quadrifoglio')

    # Estrazione date festive (Solo per Il Quadrifoglio)
    festivity_dates_fixed = set()
    festivity_dates_mobile = set()
    
    if is_quadrifoglio:
        fisse = effective_config.get('festivita_fisse', {})
        for date_val, is_active in fisse.items():
            if is_active:
                festivity_dates_fixed.add(date_val)
        
        if not fisse:
            festivity_dates_fixed.update(["01/01", "06/01", "25/04", "01/05", "02/06", "15/08", "04/10", "01/11", "08/12", "25/12", "26/12"])

        mobili_str = str(effective_config.get('festivita_mobili', '')).strip()
        for d in mobili_str.split(','):
            d = d.strip()
            if d:
                m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', d)
                if m:
                    festivity_dates_mobile.add(f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}")
                else:
                    m2 = re.search(r'(\d{1,2})[/-](\d{1,2})', d)
                    if m2:
                        festivity_dates_mobile.add(f"{int(m2.group(1)):02d}/{int(m2.group(2)):02d}")

    def _calc_selene_hours(val_str):
        t = 0.0
        for b in str(val_str).split(','):
            if '-' in b:
                try:
                    s_str, e_str = b.split('-')
                    s_str = s_str.strip().replace('.', ':')
                    if ':' not in s_str: s_str += ':00'
                    sh, sm = map(int, s_str.split(':'))
                    e_str = e_str.strip().replace('.', ':')
                    if ':' not in e_str: e_str += ':00'
                    eh, em = map(int, e_str.split(':'))
                    sd = sh + sm/60.0
                    ed = eh + em/60.0
                    if ed < sd: ed += 24.0
                    t += (ed - sd)
                except: pass
        return t

    for f in files:
        try:
            df = _read_file_safe(f, header=0)
            if len(df) <= 4: continue
            name_raw = f.stem.split('_')[0].title()
            
            effective_name = name_raw
            if name_raw in reconciliation_map:
                effective_name = reconciliation_map[name_raw]
                
            norm_name = normalize_emp_name(effective_name)
            
            if norm_name not in norm_emp_map:
                missing_employees_found.add(effective_name)
                continue
            
            orig_config_name, emp_code = norm_emp_map[norm_name]
            emp_code = str(emp_code).strip()
            if not emp_code or emp_code.lower() == 'nan':
                malformed_employees_found.add(effective_name)
                continue
            
            processed_emps += 1

            header_row = df.iloc[3]
            idx_data = find_column_index(header_row, "Data") or find_column_index_contains(header_row, 'data')
            idx_ore = find_column_index(header_row, "Ore Lavorate") or find_column_index_contains(header_row, 'ore lavorate')
            idx_det = find_column_index(header_row, "Dettagli") or find_column_index_contains(header_row, 'dettagli')
            idx_orario = find_column_index(header_row, "Orario di lavoro") or find_column_index_contains(header_row, 'orario di lavoro')
            
            memoria_orari_settimana = {}
            
            if is_selene and idx_orario is not None and idx_data is not None:
                for r_pre in range(4, len(df)):
                    row_pre = df.iloc[r_pre]
                    data_str_pre = str(row_pre[idx_data]).strip()
                    match_pre = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', data_str_pre)
                    if match_pre:
                        try:
                            d_pre = datetime.date(int(match_pre.group(3)), int(match_pre.group(2)), int(match_pre.group(1)))
                            wd = d_pre.weekday()
                            val_pre_str = str(row_pre[idx_orario]).strip()
                            orario_val_pre = _calc_selene_hours(val_pre_str)
                            if orario_val_pre > 0:
                                memoria_orari_settimana[wd] = max(memoria_orari_settimana.get(wd, 0.0), orario_val_pre)
                        except:
                            pass
                        
            elif (job_dynamic_hours_ore or job_dynamic_hours_turni) and idx_orario is not None and idx_data is not None:
                for r_pre in range(4, len(df)):
                    row_pre = df.iloc[r_pre]
                    data_str_pre = str(row_pre[idx_data]).strip()
                    match_pre = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', data_str_pre)
                    if match_pre:
                        try:
                            d_pre = datetime.date(int(match_pre.group(3)), int(match_pre.group(2)), int(match_pre.group(1)))
                            wd = d_pre.weekday()
                            val_pre_str = str(row_pre[idx_orario]).strip()
                            orario_val_pre = 0.0
                            if job_dynamic_hours_turni and '-' in val_pre_str:
                                orario_val_pre = calculate_hours_from_orario(val_pre_str)
                            elif job_dynamic_hours_ore:
                                orario_val_pre = ore_to_decimal(val_pre_str)
                            if orario_val_pre > 0:
                                memoria_orari_settimana[wd] = max(memoria_orari_settimana.get(wd, 0.0), orario_val_pre)
                        except:
                            pass

            for r in range(4, len(df)):
                row_val = df.iloc[r]
                val_data = str(row_val[idx_data]).strip()
                match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', val_data)
                if not match: continue

                giorno_int = int(match.group(1))
                mese_int = int(match.group(2))
                anno_str_full = match.group(3)
                
                anno_2 = anno_str_full[-2:]
                data_txt = f"{giorno_int:02d}{mese_int:02d}{anno_2}"
                
                date_fixed_format = f"{giorno_int:02d}/{mese_int:02d}"
                date_mobile_format = f"{giorno_int:02d}/{mese_int:02d}/{anno_str_full}"

                det_val = row_val[idx_det] if idx_det is not None else ""
                det_str = str(det_val).strip()
                if not det_str or det_str.lower() == 'nan':
                    continue
                
                giust_code = get_giustificativo_code(det_str, simple_causals_map)
                if not giust_code: 
                    causal_name_only = re.sub(r'\(.*?\)', '', det_str).strip()
                    missing_causals_found.add(causal_name_only)
                    continue

                # ========================================================
                # LOGICA FESTIVITÀ: CONTROLLO INTERCETTAZIONE (Solo Quadrifoglio)
                # ========================================================
                is_festivo = False
                if is_quadrifoglio:
                    is_festivo = (date_fixed_format in festivity_dates_fixed) or \
                                 (date_mobile_format in festivity_dates_mobile) or \
                                 (date_fixed_format in festivity_dates_mobile)
                                 
                    if is_festivo:
                        action = code_actions.get(giust_code, 'ignora')
                        if action == 'escludi':
                            continue # SALTA LA SCRITTURA DELLA RIGA
                # ========================================================

                causale_padded = giust_code.ljust(3)
                ore_dettaglio = extract_giustificativo_hours(det_str)
                
                # SE INCLUDI IN GIORNO FESTIVO DE IL QUADRIFOGLIO -> BLOCCHIAMO DIRETTAMENTE A 0 ORE
                if is_quadrifoglio and is_festivo and code_actions.get(giust_code, 'ignora') == 'includi':
                    ore_calc = 0.0
                else:
                    if ore_dettaglio > 0:
                        ore_calc = ore_dettaglio
                    else:
                        if is_selene and idx_orario is not None:
                            val_orario_str = str(row_val[idx_orario]).strip()
                            ore_da_orario = _calc_selene_hours(val_orario_str)
                            if ore_da_orario == 0.0:
                                try:
                                    d_corr = datetime.date(int(anno_str_full), int(mese_int), int(giorno_int))
                                    wd_corr = d_corr.weekday()
                                    if effective_name in actual_schedules:
                                        ore_da_orario = float(actual_schedules[effective_name].get(str(wd_corr), 0.0))
                                    else:
                                        ore_da_orario = memoria_orari_settimana.get(wd_corr, 0.0)
                                except:
                                    pass
                            
                            # CONTROLLO GRANULARE AGGIORNATO (NO has_any_schedule)
                            if ore_da_orario == 0.0 and effective_name not in actual_schedules:
                                if giust_code:
                                    employees_needing_fallback.add(effective_name)

                            ore_lavorate_effettive = ore_to_decimal(row_val[idx_ore]) if idx_ore is not None else 0.0
                            ore_calc = max(0.0, round(ore_da_orario - ore_lavorate_effettive, 2))
                            if ore_calc == 0.0:
                                ore_calc = ore_lavorate_effettive

                        elif (job_dynamic_hours_ore or job_dynamic_hours_turni) and idx_orario is not None:
                            val_orario_str = str(row_val[idx_orario]).strip()
                            ore_da_orario = 0.0
                            if job_dynamic_hours_turni and '-' in val_orario_str:
                                ore_da_orario = calculate_hours_from_orario(val_orario_str)
                            elif job_dynamic_hours_ore:
                                ore_da_orario = ore_to_decimal(val_orario_str)
                            
                            if ore_da_orario == 0.0:
                                try:
                                    d_corr = datetime.date(int(anno_str_full), int(mese_int), int(giorno_int))
                                    wd_corr = d_corr.weekday()
                                    if effective_name in actual_schedules:
                                        ore_da_orario = float(actual_schedules[effective_name].get(str(wd_corr), 0.0))
                                    else:
                                        ore_da_orario = memoria_orari_settimana.get(wd_corr, 0.0)
                                except:
                                    pass
                            
                            # CONTROLLO GRANULARE AGGIORNATO (NO has_any_schedule)
                            if ore_da_orario == 0.0 and effective_name not in actual_schedules:
                                if giust_code:
                                    employees_needing_fallback.add(effective_name)

                            ore_lavorate_effettive = ore_to_decimal(row_val[idx_ore]) if idx_ore is not None else 0.0
                            ore_calc = max(0.0, round(ore_da_orario - ore_lavorate_effettive, 2))
                            if ore_calc == 0.0:
                                ore_calc = ore_lavorate_effettive
                        else:
                            ore_calc = ore_to_decimal(row_val[idx_ore]) if idx_ore is not None else 0.0

                if is_quadrifoglio:
                    ore_int = int(ore_calc)
                    cent_int = int(round((ore_calc - ore_int) * 100))
                    ore_str = f"{ore_int:02d}{cent_int:02d}00"
                else:
                    ore_int = int(ore_calc)
                    min_int = int(round((ore_calc - ore_int) * 60))
                    ore_str = f"{ore_int:02d}{min_int:02d}00"

                if ore_calc == 0.0 and giust_code:
                    zero_hours_found.append(f"{effective_name} - {val_data}: Causale {giust_code} con 0 ore")

                line = f"{comp_code}{emp_code}{data_txt}{causale_padded}{ore_str}"
                lines.append(line)
                total_ore_count += ore_calc
        except: continue

    if employees_needing_fallback:
        conversion_tasks[task_id].update({
            'status': 'needs_fallback', 
            'progress': 100, 
            'result': sorted(list(employees_needing_fallback))
        })
        return None

    final_content = "\n".join(lines)
    return {
        'mode': 'job_txt',
        'content': final_content,
        'folder_path_resolved': folder_path,
        'company': company,
        'folder': folder_name,
        'result_data': {
            'dipendenti': processed_emps, 
            'ore': round(total_ore_count, 2), 
            'mese_anno': 'File TXT',
            'company': company,
            'missing_employees': list(missing_employees_found),
            'malformed_employees': list(malformed_employees_found),
            'missing_causals': list(missing_causals_found),
            'zero_hours': zero_hours_found 
        }
    }