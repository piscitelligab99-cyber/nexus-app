#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, time, threading, atexit, socket, errno, traceback
from pathlib import Path

HOST, PORT = "127.0.0.1", 5000
LOCKFILE_NAME, WINDOW_TITLE = "nexus_app.lock", "NEXUS | Data Conversion System"

def get_base_path():
    if getattr(sys, 'frozen', False): return Path(sys.executable).parent
    else: return Path(__file__).parent
BASE_DIR = get_base_path()

def port_is_in_use(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex((host, port)) == 0

def main():
    if port_is_in_use(HOST, PORT): 
        print("⚠️ ERRORE: La porta 5000 è occupata.")
        print("Forse la versione vecchia del programma è rimasta aperta in background!")
        print("Soluzione: Riavvia il PC oppure chiudi i processi python da Gestione Attività.")
        input("\nPremi INVIO per chiudere questa finestra...")
        sys.exit(0)
    
    # Crea Lockfile
    p = BASE_DIR / LOCKFILE_NAME
    try:
        with open(p, "w") as f: f.write(str(os.getpid()))
        atexit.register(lambda: p.unlink() if p.exists() else None)
    except: pass

    os.chdir(str(BASE_DIR))
    if not getattr(sys, 'frozen', False): print("💎 NEXUS - DATA CONVERSION SYSTEM")

    try:
        from main import app
        import webview
    except Exception as e:
        print("\n❌ ERRORE CRITICO DI IMPORTAZIONE:\n")
        traceback.print_exc()
        input("\nFAI UNO SCREENSHOT E MANDAMELO! Premi INVIO per chiudere...")
        sys.exit(1)

    # Avvia Flask in background
    t = threading.Thread(target=lambda: app.run(host=HOST, port=PORT, debug=False, use_reloader=False), daemon=True)
    t.start()
    
    time.sleep(1)
    
    # Adesso puntiamo all'indirizzo del server Flask, non al file locale!
    server_url = f'http://{HOST}:{PORT}/'
    
    try:
        webview.create_window(WINDOW_TITLE, server_url, width=1200, height=850, resizable=True, min_size=(950, 700), background_color='#f3f6fc')
        webview.start()
    except Exception as e:
        print("\n❌ ERRORE NELL'AVVIO DELL'INTERFACCIA GRAFICA:\n")
        traceback.print_exc()
        input("\nPremi INVIO per chiudere...")

if __name__ == '__main__': 
    try:
        main()
    except Exception as e:
        print("\n❌ ERRORE IMPREVISTO:\n")
        traceback.print_exc()
        input("\nFAI UNO SCREENSHOT E MANDAMELO! Premi INVIO per chiudere...")