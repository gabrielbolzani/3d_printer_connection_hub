import os
import sys
import json
import shutil
import threading
import socket
import webbrowser
import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image
import pystray
from pystray import MenuItem as item

# ---------------------------------------------------------------------------
# Descoberta do diretório de trabalho (config.json, auth_token.json)
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # Executável compilado: dados em %APPDATA%\AditivaFlowHub
    CONFIG_DIR = os.path.join(os.environ.get('APPDATA', ''), 'AditivaFlowHub')
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.chdir(CONFIG_DIR)
    sys.path.insert(0, sys._MEIPASS)
else:
    # Rodando pelo Python direto: raiz do repositório
    CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    os.chdir(CONFIG_DIR)
    sys.path.insert(0, CONFIG_DIR)

CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

import app as server_app
from werkzeug.serving import make_server

# ---------------------------------------------------------------------------
class HubLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("AditivaFlow Hub")
        self.root.resizable(False, False)

        self.server_thread = None
        self.server = None

        self.setup_icon()
        self.setup_ui()
        self.setup_tray()

        # "X" apenas esconde; use o botão "Encerrar" para fechar de verdade
        self.root.protocol('WM_DELETE_WINDOW', self.hide_window)

        self.check_status_loop()

    # ------------------------------------------------------------------
    # Ícone
    # ------------------------------------------------------------------
    def setup_icon(self):
        self.tray_image = None
        base_dir = sys._MEIPASS if getattr(sys, 'frozen', False) else CONFIG_DIR

        ico_path = os.path.join(base_dir, 'favicon.ico')
        png_path = os.path.join(base_dir, 'favicon-32x32.png')

        # Janela / barra de tarefas / Alt+Tab → .ico obrigatório no Windows
        if os.path.exists(ico_path):
            try:
                self.root.iconbitmap(default=ico_path)
            except Exception as e:
                print(f"iconbitmap: {e}")

        # System Tray → PNG via Pillow
        if os.path.exists(png_path):
            try:
                self.tray_image = Image.open(png_path).convert("RGBA")
            except Exception as e:
                print(f"tray image: {e}")

        if self.tray_image is None:
            self.tray_image = Image.new('RGBA', (32, 32), color=(30, 100, 200, 255))

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------
    def setup_ui(self):
        self.root.configure(bg="#1a1a1a")

        w, h = 420, 530
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f'{w}x{h}+{x}+{y}')

        # Título
        tk.Label(self.root, text="AditivaFlow Hub",
                 font=("Segoe UI", 18, "bold"), fg="#ffffff", bg="#1a1a1a",
                 pady=16).pack()

        # Status
        self.status_label = tk.Label(self.root, text="Servidor: Parado",
                                     font=("Segoe UI", 12), fg="#ff5555", bg="#1a1a1a")
        self.status_label.pack(pady=6)

        # Ligar / Desligar
        self.btn_toggle = tk.Button(self.root, text="LIGAR SERVIDOR",
                                    font=("Segoe UI", 10, "bold"),
                                    bg="#22c55e", fg="white", width=22, height=2,
                                    command=self.toggle_server, relief="flat", cursor="hand2")
        self.btn_toggle.pack(pady=8)

        # Abrir navegador
        tk.Button(self.root, text="ABRIR NO NAVEGADOR",
                  font=("Segoe UI", 10), bg="#3b82f6", fg="white",
                  width=22, relief="flat", command=self.open_browser,
                  cursor="hand2").pack(pady=4)

        # ---------- Seção Config ----------
        sep_frame = tk.Frame(self.root, bg="#2a2a2a", height=1)
        sep_frame.pack(fill="x", padx=20, pady=12)

        tk.Label(self.root, text="Configuração", font=("Segoe UI", 9, "bold"),
                 fg="#777777", bg="#1a1a1a").pack()

        # Caminho atual do config
        short_path = CONFIG_FILE if len(CONFIG_FILE) < 55 else "…" + CONFIG_FILE[-52:]
        self.config_path_label = tk.Label(self.root,
                                          text=short_path,
                                          font=("Courier New", 7), fg="#555555",
                                          bg="#1a1a1a", wraplength=380)
        self.config_path_label.pack(pady=2)

        btn_row = tk.Frame(self.root, bg="#1a1a1a")
        btn_row.pack(pady=6)

        tk.Button(btn_row, text="📂 Importar Config",
                  font=("Segoe UI", 9), bg="#6d28d9", fg="white",
                  width=17, relief="flat", command=self.import_config,
                  cursor="hand2").pack(side="left", padx=4)

        tk.Button(btn_row, text="📁 Abrir Pasta Config",
                  font=("Segoe UI", 9), bg="#374151", fg="white",
                  width=17, relief="flat", command=self.open_config_folder,
                  cursor="hand2").pack(side="left", padx=4)

        # ---------- Startup ----------
        sep2 = tk.Frame(self.root, bg="#2a2a2a", height=1)
        sep2.pack(fill="x", padx=20, pady=12)

        self.startup_var = tk.BooleanVar(value=self.check_startup_status())
        tk.Checkbutton(self.root, text="Iniciar com o Windows (minimizado na bandeja)",
                       variable=self.startup_var,
                       bg="#1a1a1a", fg="#aaaaaa", activebackground="#1a1a1a",
                       selectcolor="#1a1a1a", command=self.toggle_startup).pack()

        tk.Label(self.root,
                 text="(Fechar a janela pelo 'X' apenas minimiza para a bandeja)",
                 font=("Segoe UI", 7, "italic"), fg="#555555", bg="#1a1a1a").pack(pady=2)

        # ---------- Encerrar ----------
        tk.Button(self.root, text="ENCERRAR APLICATIVO",
                  font=("Segoe UI", 9, "bold"),
                  bg="#3f3f3f", fg="#ffcccc", width=22, relief="flat",
                  command=self.quit_app, cursor="hand2").pack(pady=10)

        tk.Label(self.root, text="v1.0.4 - aditivaflow.com.br",
                 font=("Segoe UI", 8), fg="#333333", bg="#1a1a1a").pack(side="bottom", pady=8)

    # ------------------------------------------------------------------
    # System Tray
    # ------------------------------------------------------------------
    def setup_tray(self):
        menu = (item('Abrir Dashboard', self.open_browser),
                item('Exibir Janela', self.show_window),
                item('Ligar/Desligar Servidor', self.toggle_server),
                item('Encerrar Hub', self.quit_app))
        self.tray_icon = pystray.Icon("AditivaFlow", self.tray_image, "AditivaFlow Hub", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_window(self):
        self.root.withdraw()

    def show_window(self):
        self.root.after(0, self.root.deiconify)

    def quit_app(self):
        if messagebox.askyesno("Encerrar", "Desligar o servidor e fechar o Hub?"):
            self.stop_server()
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.root.quit()
            os._exit(0)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def is_server_running(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(('127.0.0.1', 5000)) == 0

    def check_status_loop(self):
        if self.is_server_running():
            self.status_label.config(text="Servidor: ATIVO ●", fg="#22c55e")
            self.btn_toggle.config(text="DESLIGAR SERVIDOR", bg="#ef4444", state="normal")
        else:
            self.status_label.config(text="Servidor: PARADO ●", fg="#ff5555")
            self.btn_toggle.config(text="LIGAR SERVIDOR", bg="#22c55e", state="normal")
        self.root.after(2000, self.check_status_loop)

    # ------------------------------------------------------------------
    # Servidor
    # ------------------------------------------------------------------
    def toggle_server(self):
        self.btn_toggle.config(state="disabled")
        if self.is_server_running():
            self.stop_server()
        else:
            self.start_server()

    def run_flask(self):
        try:
            self.server = make_server('0.0.0.0', 5000, server_app.app)
            self.server.serve_forever()
        except Exception as e:
            print(f"Flask erro: {e}")

    def start_server(self):
        if self.is_server_running():
            return
        server_app.start_background_tasks()
        self.server_thread = threading.Thread(target=self.run_flask, daemon=True)
        self.server_thread.start()

    def stop_server(self):
        server_app.KEEP_RUNNING = False
        for p in server_app.PRINTERS:
            try:
                p.stop()
            except Exception:
                pass
        if self.server:
            try:
                self.server.shutdown()
            except Exception:
                pass
        self.server = None

    def open_browser(self):
        webbrowser.open("http://127.0.0.1:5000")

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def import_config(self):
        """Permite ao usuário escolher um config.json externo e copiá-lo."""
        was_running = self.is_server_running()
        if was_running:
            if not messagebox.askyesno("Importar Config",
                                       "O servidor será parado para importar o config.\nContinuar?"):
                return
            self.stop_server()

        path = filedialog.askopenfilename(
            title="Selecione o arquivo config.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            # Valida se é um JSON válido antes de substituir
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, list):
                messagebox.showerror("Erro", "O arquivo selecionado não é um config válido (deve ser uma lista JSON).")
                return

            # Faz backup do config atual se existir
            if os.path.exists(CONFIG_FILE):
                backup = CONFIG_FILE + '.bak'
                shutil.copy2(CONFIG_FILE, backup)

            shutil.copy2(path, CONFIG_FILE)
            messagebox.showinfo("Sucesso",
                                f"Config importado com sucesso!\n"
                                f"{len(data)} impressora(s) carregada(s).\n\n"
                                f"Dica: backup do config anterior salvo em:\n{CONFIG_FILE}.bak")

        except json.JSONDecodeError:
            messagebox.showerror("Erro", "O arquivo selecionado não é um JSON válido.")
        except Exception as e:
            messagebox.showerror("Erro ao importar", str(e))

        if was_running:
            self.start_server()

    def open_config_folder(self):
        """Abre o Explorer na pasta onde o config.json está salvo."""
        os.startfile(CONFIG_DIR)

    # ------------------------------------------------------------------
    # Startup do Windows
    # ------------------------------------------------------------------
    def toggle_startup(self):
        startup_folder = os.path.join(os.environ.get('APPDATA', ''),
                                      'Microsoft', 'Windows', 'Start Menu',
                                      'Programs', 'Startup')
        shortcut_path = os.path.join(startup_folder, 'AditivaFlowHub.bat')

        if self.startup_var.get():
            with open(shortcut_path, "w") as f:
                f.write('@echo off\n')
                if getattr(sys, 'frozen', False):
                    f.write(f'start "" "{sys.executable}" --minimized\n')
                else:
                    f.write(f'cd /d "{CONFIG_DIR}"\n')
                    f.write(f'start pythonw "{os.path.abspath(__file__)}" --minimized\n')
            messagebox.showinfo("Startup", "O Hub iniciará automaticamente com o Windows!")
        else:
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)

    def check_startup_status(self):
        startup_folder = os.path.join(os.environ.get('APPDATA', ''),
                                      'Microsoft', 'Windows', 'Start Menu',
                                      'Programs', 'Startup')
        return os.path.exists(os.path.join(startup_folder, 'AditivaFlowHub.bat'))


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app_gui = HubLauncher(root)

    if "--minimized" in sys.argv:
        root.withdraw()

    root.mainloop()
