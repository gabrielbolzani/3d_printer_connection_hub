import tkinter as tk
from tkinter import messagebox
import subprocess
import threading
import os
import sys
import time
import socket
import webbrowser
from pathlib import Path
from PIL import Image, ImageTk
import pystray
from pystray import MenuItem as item

# AditivaFlow Hub - Windows GUI Launcher
# Improved version with System Tray and Hidden Terminal

class HubLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("AditivaFlow Hub")
        self.root.geometry("400x380")
        self.root.resizable(False, False)
        
        self.server_process = None
        self.repo_root = Path(__file__).parent.parent.parent.absolute()
        self.venv_path = self.repo_root / "venv"
        self.python_exe = self.venv_path / "Scripts" / "pythonw.exe" # Use pythonw to hide console
        
        self.icon_path = self.repo_root / "favicon-32x32.png"
        self.setup_icon()
        
        self.setup_ui()
        self.setup_tray()
        
        # Override close button to minimize to tray
        self.root.protocol('WM_DELETE_WINDOW', self.hide_window)
        
        self.check_status_loop()

    def setup_icon(self):
        try:
            if self.icon_path.exists():
                img = Image.open(self.icon_path)
                self.photo = ImageTk.PhotoImage(img)
                self.root.iconphoto(False, self.photo)
                self.tray_image = img
            else:
                # Fallback empty image
                self.tray_image = Image.new('RGB', (32, 32), color='blue')
        except Exception as e:
            print(f"Icon error: {e}")
            self.tray_image = Image.new('RGB', (32, 32), color='blue')

    def setup_ui(self):
        self.root.configure(bg="#1a1a1a")
        
        # Centering window
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width/2) - (400/2)
        y = (screen_height/2) - (380/2)
        self.root.geometry('%dx%d+%d+%d' % (400, 380, x, y))

        title_label = tk.Label(self.root, text="AditivaFlow Hub", font=("Segoe UI", 18, "bold"), fg="#ffffff", bg="#1a1a1a", pady=20)
        title_label.pack()

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
        self.chk_startup.pack(pady=15)

        info_label = tk.Label(self.root, text="(O app continuará rodando na bandeja)", font=("Segoe UI", 8), fg="#666666", bg="#1a1a1a")
        info_label.pack()

        footer = tk.Label(self.root, text="v1.0.0 - aditivaflow.com.br", font=("Segoe UI", 8), fg="#444444", bg="#1a1a1a")
        footer.pack(side="bottom", pady=10)

    def setup_tray(self):
        menu = (item('Abrir Hub', self.show_window), 
                item('Ligar/Desligar', self.toggle_server),
                item('Sair', self.quit_app))
        self.tray_icon = pystray.Icon("AditivaFlow", self.tray_image, "AditivaFlow Hub", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_window(self):
        self.root.withdraw()
        # Optional: notification
        # self.tray_icon.notify("O Hub continua rodando em segundo plano.", "AditivaFlow Hub")

    def show_window(self):
        self.root.after(0, self.root.deiconify)

    def quit_app(self):
        self.stop_server()
        self.tray_icon.stop()
        self.root.quit()

    def is_server_running(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(('localhost', 5000)) == 0

    def check_status_loop(self):
        running = self.is_server_running()
        if running:
            self.status_label.config(text="Servidor: ATIVO", fg="#22c55e")
            self.btn_toggle.config(text="DESLIGAR SERVIDOR", bg="#ef4444")
        else:
            self.status_label.config(text="Servidor: PARADO", fg="#ff5555")
            self.btn_toggle.config(text="LIGAR SERVIDOR", bg="#22c55e")
        
        self.root.after(2000, self.check_status_loop)

    def toggle_server(self):
        if self.is_server_running():
            self.stop_server()
        else:
            self.start_server()

    def start_server(self):
        if not self.python_exe.exists():
            # Try plain python if pythonw not in venv yet
            self.python_exe = self.venv_path / "Scripts" / "python.exe"
            if not self.python_exe.exists():
                messagebox.showinfo("Instalação", "Ambiente não encontrado. Instalando dependências...")
                threading.Thread(target=self.initial_setup).start()
                return

        threading.Thread(target=self._run_server, daemon=True).start()

    def _run_server(self):
        try:
            # CREATE_NO_WINDOW = 0x08000000 -> hides the console completely
            self.server_process = subprocess.Popen(
                [str(self.python_exe), "app.py"],
                cwd=str(self.repo_root),
                creationflags=0x08000000 if os.name == 'nt' else 0
            )
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao iniciar: {e}")

    def stop_server(self):
        try:
            # Clean kill of python processes running app.py
            if os.name == 'nt':
                subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/T"], capture_output=True)
                subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe", "/T"], capture_output=True)
        except:
            pass

    def open_browser(self):
        webbrowser.open("http://localhost:5000")

    def initial_setup(self):
        try:
            self.btn_toggle.config(state="disabled", text="INSTALANDO...")
            subprocess.run([sys.executable, "-m", "venv", str(self.venv_path)], cwd=str(self.repo_root), check=True)
            pip_exe = self.venv_path / "Scripts" / "pip.exe"
            subprocess.run([str(pip_exe), "install", "-r", "requirements.txt"], cwd=str(self.repo_root), check=True)
            # Switch to pythonw for next time
            self.python_exe = self.venv_path / "Scripts" / "pythonw.exe"
            messagebox.showinfo("Sucesso", "Instalação concluída! Você já pode ligar o servidor.")
        except Exception as e:
            messagebox.showerror("Erro na instalação", str(e))
        finally:
            self.btn_toggle.config(state="normal", text="LIGAR SERVIDOR")

    def toggle_startup(self):
        startup_folder = Path(os.getenv('APPDATA')) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        shortcut_path = startup_folder / "AditivaFlowHub.bat"
        
        if self.startup_var.get():
            with open(shortcut_path, "w") as f:
                f.write(f"@echo off\n")
                f.write(f"cd /d \"{self.repo_root}\"\n")
                # Start the launcher itself in hidden mode
                f.write(f"start pythonw \"{Path(__file__).absolute()}\" --minimized\n")
            messagebox.showinfo("Startup", "O Hub iniciará minimizado com o Windows!")
        else:
            if shortcut_path.exists():
                shortcut_path.unlink()

    def check_startup_status(self):
        startup_folder = Path(os.getenv('APPDATA')) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        return (startup_folder / "AditivaFlowHub.bat").exists()

if __name__ == "__main__":
    root = tk.Tk()
    app = HubLauncher(root)
    
    # Check if started minimized
    if "--minimized" in sys.argv:
        root.withdraw()
        
    root.mainloop()
