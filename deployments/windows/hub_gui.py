import os
import sys
import threading
import time
import socket
import webbrowser
import tkinter as tk
from tkinter import messagebox
from PIL import Image
import pystray
from pystray import MenuItem as item

# Configuração de diretórios compatível com PyInstaller
if getattr(sys, 'frozen', False):
    CONFIG_DIR = os.path.join(os.environ.get('APPDATA', ''), 'AditivaFlowHub')
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.chdir(CONFIG_DIR)
    sys.path.insert(0, sys._MEIPASS)
else:
    REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    os.chdir(REPO_ROOT)
    sys.path.insert(0, REPO_ROOT)

import app as server_app
from werkzeug.serving import make_server

class HubLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("AditivaFlow Hub")
        self.root.geometry("400x420")
        self.root.resizable(False, False)
        
        self.server_thread = None
        self.server = None
        
        self.setup_icon()
        self.setup_ui()
        self.setup_tray()
        
        # O "X" da janela apenas esconde, não encerra
        self.root.protocol('WM_DELETE_WINDOW', self.hide_window)
        
        self.check_status_loop()

    def setup_icon(self):
        """
        No Windows, a única forma 100% confiável de definir o ícone da 
        janela, da barra de tarefas e do Alt+Tab é usar iconbitmap com um
        arquivo .ico. O iconphoto com PNG muitas vezes cai na pena padrão.
        """
        self.tray_image = None
        
        if getattr(sys, 'frozen', False):
            # Dentro do executável PyInstaller
            base_dir = sys._MEIPASS
        else:
            # Rodando direto pelo Python
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        
        ico_path = os.path.join(base_dir, 'favicon.ico')
        png_path = os.path.join(base_dir, 'favicon-32x32.png')
        
        # Ícone da Janela / Barra de Tarefas / Alt+Tab (requer .ico no Windows)
        if os.path.exists(ico_path):
            try:
                self.root.iconbitmap(default=ico_path)
            except Exception as e:
                print(f"Aviso iconbitmap: {e}")
        
        # Ícone da Bandeja (System Tray) — usa PNG via Pillow
        if os.path.exists(png_path):
            try:
                self.tray_image = Image.open(png_path).convert("RGBA")
            except Exception as e:
                print(f"Aviso tray image: {e}")
        
        if self.tray_image is None:
            # Fallback: quadrado azul simples
            self.tray_image = Image.new('RGBA', (32, 32), color=(30, 100, 200, 255))

    def setup_ui(self):
        self.root.configure(bg="#1a1a1a")
        
        # Centralizar na tela
        x = (self.root.winfo_screenwidth()//2) - (400//2)
        y = (self.root.winfo_screenheight()//2) - (450//2)
        self.root.geometry(f'400x450+{x}+{y}')

        title = tk.Label(self.root, text="AditivaFlow Hub", font=("Segoe UI", 18, "bold"), fg="#ffffff", bg="#1a1a1a", pady=20)
        title.pack()

        self.status_label = tk.Label(self.root, text="Servidor: Parado", font=("Segoe UI", 12), fg="#ff5555", bg="#1a1a1a")
        self.status_label.pack(pady=10)

        self.btn_toggle = tk.Button(self.root, text="LIGAR SERVIDOR", font=("Segoe UI", 10, "bold"), 
                                  bg="#22c55e", fg="white", width=20, height=2, 
                                  command=self.toggle_server, relief="flat", cursor="hand2")
        self.btn_toggle.pack(pady=10)

        self.btn_browser = tk.Button(self.root, text="ABRIR NO NAVEGADOR", font=("Segoe UI", 10), 
                                   bg="#3b82f6", fg="white", width=20, relief="flat",
                                   command=self.open_browser, cursor="hand2")
        self.btn_browser.pack(pady=5)

        self.startup_var = tk.BooleanVar()
        self.startup_var.set(self.check_startup_status())
        self.chk_startup = tk.Checkbutton(self.root, text="Iniciar com o Windows (Minimizado)", variable=self.startup_var,
                                        bg="#1a1a1a", fg="#aaaaaa", activebackground="#1a1a1a", 
                                        selectcolor="#1a1a1a", command=self.toggle_startup)
        self.chk_startup.pack(pady=10)

        info_label = tk.Label(self.root, text="(Use o 'X' na janela apenas para minimizar para a bandeja)", font=("Segoe UI", 8, "italic"), fg="#888888", bg="#1a1a1a")
        info_label.pack()

        # Botão explícito de Sair
        self.btn_quit = tk.Button(self.root, text="ENCERRAR APLICATIVO", font=("Segoe UI", 9, "bold"), 
                                  bg="#444444", fg="#ffdddd", width=20, relief="flat",
                                  command=self.quit_app, cursor="hand2")
        self.btn_quit.pack(pady=10)

        footer = tk.Label(self.root, text="v1.0.3 - aditivaflow.com.br", font=("Segoe UI", 8), fg="#444444", bg="#1a1a1a")
        footer.pack(side="bottom", pady=10)

    def setup_tray(self):
        menu = (item('Abrir Dashboard', self.open_browser),
                item('Exibir Tela', self.show_window), 
                item('Ligar/Desligar', self.toggle_server),
                item('Encerrar Hub', self.quit_app))
        self.tray_icon = pystray.Icon("AditivaFlow", self.tray_image, "AditivaFlow Hub", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_window(self):
        self.root.withdraw()

    def show_window(self):
        self.root.after(0, self.root.deiconify)

    def quit_app(self):
        if messagebox.askyesno("Encerrar", "Tem certeza que deseja desligar o servidor e fechar o aplicativo completamente?"):
            self.stop_server()
            if hasattr(self, 'tray_icon'):
                self.tray_icon.stop()
            self.root.quit()
            os._exit(0)

    def is_server_running(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            # Verifica se a porta 5000 está ocupada
            return s.connect_ex(('127.0.0.1', 5000)) == 0

    def check_status_loop(self):
        running = self.is_server_running()
        if running:
            self.status_label.config(text="Servidor: ATIVO", fg="#22c55e")
            self.btn_toggle.config(text="DESLIGAR SERVIDOR", bg="#ef4444", state="normal")
        else:
            self.status_label.config(text="Servidor: PARADO", fg="#ff5555")
            self.btn_toggle.config(text="LIGAR SERVIDOR", bg="#22c55e", state="normal")
        
        self.root.after(2000, self.check_status_loop)

    def toggle_server(self):
        self.btn_toggle.config(state="disabled")
        if self.is_server_running():
            self.stop_server()
        else:
            self.start_server()

    # Executa o servidor Flask na nossa própria thread
    def run_flask(self):
        try:
            self.server = make_server('0.0.0.0', 5000, server_app.app)
            self.server.serve_forever()
        except Exception as e:
            print(f"Flask falhou ao iniciar: {e}")

    def start_server(self):
        if self.is_server_running(): return
        
        # Inicia tarefas em background direto do app.py
        server_app.start_background_tasks()
        
        # Inicia o Web Server
        self.server_thread = threading.Thread(target=self.run_flask, daemon=True)
        self.server_thread.start()

    def stop_server(self):
        server_app.KEEP_RUNNING = False
        
        # Interrompe drivers de impressora
        for p in server_app.PRINTERS:
            try: p.stop()
            except: pass
            
        # Desliga servidor Werkzeug
        if self.server:
            try: self.server.shutdown()
            except: pass
        self.server = None

    def open_browser(self):
        webbrowser.open("http://127.0.0.1:5000")

    def toggle_startup(self):
        startup_folder = os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
        shortcut_path = os.path.join(startup_folder, 'AditivaFlowHub.bat')
        
        if self.startup_var.get():
            with open(shortcut_path, "w") as f:
                f.write('@echo off\n')
                if getattr(sys, 'frozen', False):
                    # Inicia minimizado direto do executável
                    f.write(f'start "" "{sys.executable}" --minimized\n')
                else:
                    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
                    f.write(f'cd /d "{repo_root}"\n')
                    f.write(f'start pythonw "{os.path.abspath(__file__)}" --minimized\n')
            messagebox.showinfo("Startup", "O Hub iniciará automaticamente junto com o Windows!")
        else:
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)

    def check_startup_status(self):
        startup_folder = os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
        return os.path.exists(os.path.join(startup_folder, 'AditivaFlowHub.bat'))

if __name__ == "__main__":
    root = tk.Tk()
    app = HubLauncher(root)
    
    if "--minimized" in sys.argv:
        root.withdraw()
        
    root.mainloop()
