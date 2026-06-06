// Static/script.js

const API_BASE = '/api';
let uploadedFilesStore = []; // Array in memoria RAM per stoccare i file trascinati dall'utente

// ===== APPLICAZIONE PATTERN: ESTRAZIONE TENANT ID DALL'URL =====
function getTenantIdFromUrl() {
    const pathParts = window.location.pathname.split('/');
    const empresaIdx = pathParts.indexOf('azienda');
    if (empresaIdx !== -1 && pathParts[empresaIdx + 1]) {
        return decodeURIComponent(pathParts[empresaIdx + 1]);
    }
    return null;
}

// ===== INIZIALIZZAZIONE ALL'AVVIO =====
document.addEventListener('DOMContentLoaded', () => {
    const tenantId = getTenantIdFromUrl();
    if (!tenantId) {
        showMessage("Impossibile inizializzare l'ambiente: Tenant ID mancante nell'URL.", "error");
        return;
    }

    // Aggiorna l'interfaccia con il nome dell'azienda corrente
    document.getElementById('tenantDisplayBadge').textContent = `Spazio Isolato: ${tenantId.toUpperCase()}`;

    // Carica la configurazione anagrafica specifica del cliente
    loadJobConfig(tenantId);
    
    // Inizializza gli ascoltatori visivi per l'area di Drag & Drop
    initDragAndDropLogic();
});

// ===== VISUALIZZAZIONE POPUP NOTIFICHE =====
function showMessage(msg, type = 'info') { 
    const container = document.getElementById('messageContainer'); 
    container.innerHTML = `<div class="message ${type}">${msg}</div>`; 
    setTimeout(() => container.innerHTML = '', 4000); 
}

// ===== ABILITAZIONE EVENTI GESTIONE FILE (DRAG & DROP) =====
function initDragAndDropLogic() {
    const dropZone = document.getElementById('dropZoneJob');
    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => { e.preventDefault(); e.stopPropagation(); }, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('filled'), false);
    });
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('filled'), false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        processSelectedFiles(files);
    }, false);
}

function triggerFileInputJob() {
    document.getElementById('fileInputJob').click();
}

function handleFileSelectionJob(e) {
    processSelectedFiles(e.target.files);
}

function processSelectedFiles(files) {
    if (files.length === 0) return;

    const validExtensions = ['.xlsx', '.xls', '.csv'];
    
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const filename = file.name.toLowerCase();
        const isValid = validExtensions.some(ext => filename.endsWith(ext));
        
        if (isValid) {
            if (!uploadedFilesStore.some(f => f.name === file.name && f.size === file.size)) {
                uploadedFilesStore.push(file);
            }
        }
    }

    const statusText = document.getElementById('uploadStatusText');
    if (uploadedFilesStore.length > 0) {
        statusText.innerHTML = `📚 <b>${uploadedFilesStore.length} file pronti</b> per l'invio`;
        document.getElementById('dropZoneJob').style.borderColor = '#10b981';
    }
}

// ===== GESTIONE DELLE RIGHE DINAMICHE IN TABELLA =====
function addJobEmployeeRow(name = '', code = '') {
    const body = document.getElementById('jobEmployeeBody');
    const row = document.createElement('tr');
    row.innerHTML = `
        <td><input type="text" class="emp-name" value="${name}" placeholder="es. Mario Rossi"></td>
        <td><input type="text" class="emp-code code-field" value="${code}" placeholder="Codice JOB"></td>
        <td style="text-align:center;"><button onclick="this.parentElement.parentElement.remove(); updateCounts();" class="special-badge">✕</button></td>
    `;
    body.appendChild(row);
    updateCounts();
}

function addJobCausalRow(name = '', code = '', festivityAction = 'ignora') {
    const body = document.getElementById('jobCausalBody');
    const row = document.createElement('tr');
    row.innerHTML = `
        <td><input type="text" class="caus-name" value="${name}" placeholder="es. Ferie"></td>
        <td><input type="text" class="caus-code code-field" value="${code}" placeholder="es. FE"></td>
        <td>
            <select class="caus-festivity" style="width: 100%; padding: 6px; border: 1px solid #cbd5e1; border-radius: 8px; font-size:13px;">
                <option value="ignora" ${festivityAction === 'ignora' ? 'selected' : ''}>-- Ignora --</option>
                <option value="escludi" ${festivityAction === 'escludi' ? 'selected' : ''}>🔴 Escludi</option>
                <option value="includi" ${festivityAction === 'includi' ? 'selected' : ''}>🟢 Includi</option>
            </select>
        </td>
        <td style="text-align:center;"><button onclick="this.parentElement.parentElement.remove()" class="special-badge">✕</button></td>
    `;
    body.appendChild(row);
}

function updateCounts() {
    const rows = document.querySelectorAll('#jobEmployeeBody tr').length;
    document.getElementById('jobEmpCount').textContent = `(${rows})`;
}

function clearJobEmployees() {
    if (confirm("Vuoi svuotare l'elenco dei dipendenti della tabella attuale?")) {
        document.getElementById('jobEmployeeBody').innerHTML = '';
        updateCounts();
    }
}

// ===== CHIAMATE API: CARICAMENTO E SALVATAGGIO CONFIGURAZIONI TRAMITE TENANT ID =====
async function loadJobConfig(tenantId) {
    try {
        const res = await fetch(`${API_BASE}/job/config/${encodeURIComponent(tenantId)}`);
        const data = await res.json();
        if (data.success && data.config) {
            Object.entries(data.config.employees || {}).forEach(([name, code]) => addJobEmployeeRow(name, code));
            Object.entries(data.config.causals || {}).forEach(([name, c]) => {
                if (typeof c === 'object') {
                    addJobCausalRow(name, c.code, c.festivity_action);
                } else {
                    addJobCausalRow(name, c, 'ignora');
                }
            });
        }
    } catch(e) {
        showMessage('Nessuna anagrafica pregressa trovata per questo tenant.', 'info');
    }
}

async function saveJobConfig() {
    const tenantId = getTenantIdFromUrl();
    if (!tenantId) return;

    const configToSave = { employees: {}, causals: {} };

    document.querySelectorAll('#jobEmployeeBody tr').forEach(row => {
        const name = row.querySelector('.emp-name').value.trim();
        const code = row.querySelector('.emp-code').value.trim();
        if (name) configToSave.employees[name] = code;
    });
    
    document.querySelectorAll('#jobCausalBody tr').forEach(row => {
        const name = row.querySelector('.caus-name').value.trim();
        const code = row.querySelector('.caus-code').value.trim();
        const festivity = row.querySelector('.caus-festivity').value;
        if (name) configToSave.causals[name] = { code: code, festivity_action: festivity };
    });

    try {
        const res = await fetch(`${API_BASE}/job/config/${encodeURIComponent(tenantId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config: configToSave })
        });
        const data = await res.json();
        if (data.success) showMessage('Anagrafica tenant salvata!', 'success');
    } catch(e) {
        showMessage('Errore durante il salvataggio dei dati.', 'error');
    }
}

// ===== CHIAMATA API: CARICAMENTO MULTIPART DI FILE FISICI REALI =====
async function startJobConversion() {
    const tenantId = getTenantIdFromUrl();
    if (!tenantId) return;

    if (uploadedFilesStore.length === 0) {
        return showMessage('Trascina o seleziona almeno un file prima di procedere!', 'error');
    }

    await saveJobConfig();

    const btn = document.getElementById('btnStartJob');
    btn.disabled = true;
    btn.textContent = '⏳ Elaborazione in RAM...';

    try {
        const fd = new FormData();
        
        uploadedFilesStore.forEach(file => {
            fd.append('files', file);
        });

        fd.append('job_dynamic_hours_ore', document.getElementById('jobDynamicHoursOre').checked);
        fd.append('job_dynamic_hours_turni', document.getElementById('jobDynamicHoursTurni').checked);

        const res = await fetch(`${API_BASE}/start-conversion/${encodeURIComponent(tenantId)}`, { method: 'POST', body: fd });
        const data = await res.json();
        
        if (data.success) {
            showMessage('Elaborazione completata! Download in corso...', 'success');
            
            const blob = new Blob([data.fileContent], { type: 'text/plain' });
            const link = document.createElement('a');
            link.href = window.URL.createObjectURL(blob);
            link.download = data.fileName;
            link.click();
            
            uploadedFilesStore = [];
            document.getElementById('uploadStatusText').textContent = 'Trascina qui i file Excel o CSV';
            document.getElementById('dropZoneJob').style.borderColor = '#cbd5e1';
        } else {
            showMessage(data.message, 'error');
        }
    } catch(e) {
        showMessage(`Errore di rete: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '⚡ Genera Tracciato Paghe';
    }
}
