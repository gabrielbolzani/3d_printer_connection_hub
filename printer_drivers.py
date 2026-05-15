import json
import socket
import threading
import time
import queue
import ssl
import requests
import struct
import select
import paho.mqtt.client as mqtt
import ftplib
import zipfile
import io
import base64
import xml.etree.ElementTree as ET
import sys
import os
import subprocess
from datetime import datetime, timedelta
import atexit
from logger_config import log_info, log_error, log_debug, log_warn

FFMPEG_PROCESSES = []

def _cleanup_ffmpegs():
    global FFMPEG_PROCESSES
    for proc in FFMPEG_PROCESSES:
        try:
            if proc and proc.poll() is None:
                proc.kill()
        except: pass
    FFMPEG_PROCESSES.clear()

atexit.register(_cleanup_ffmpegs)

def get_ffmpeg_path():
    import shutil
    import zipfile
    import platform
    
    # 1. Buscar no PATH do sistema
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path: return ffmpeg_path
    
    # 2. Local persistente do AditivaFlow no AppData (sobrevive ao PyInstaller)
    base_dir = os.environ.get('APPDATA', os.path.expanduser('~'))
    local_bin = os.path.join(base_dir, "AditivaFlowHub", "bin")
    if sys.platform == "win32":
        local_ffmpeg = os.path.join(local_bin, "ffmpeg.exe")
    else:
        local_ffmpeg = os.path.join(local_bin, "ffmpeg")
        
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
        
    # 3. Baixar automaticamente para usuários de Windows
    if sys.platform == "win32":
        try:
            log_info(f"[System] FFmpeg não encontrado localmente. Baixando dependência em segundo plano (Apenas na primeira vez)...")
            os.makedirs(local_bin, exist_ok=True)
            zip_path = os.path.join(local_bin, "ffmpeg.zip")
            url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
            
            # Usando powershell silencioso para evitar dependências de SSL nativo
            subprocess.run(["powershell", "-Command", f"$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '{url}' -OutFile '{zip_path}'"], check=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    if member.endswith("ffmpeg.exe"):
                        source = zip_ref.open(member)
                        target = open(local_ffmpeg, "wb")
                        with source, target:
                            shutil.copyfileobj(source, target)
                        break
            
            try: os.remove(zip_path)
            except: pass
            
            log_info("[System] FFmpeg baixado com sucesso! A câmera agora está habilitada.")
            if os.path.exists(local_ffmpeg):
                return local_ffmpeg
        except Exception as e:
            log_error(f"[System] Falha ao tentar baixar o FFmpeg de forma automatizada: {e}")
            
    # 4. Outros caminhos de fallback
    common_paths = [
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "/snap/bin/ffmpeg"
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path
            
    return None



# Bambu Lab Filament Mapping
BAMBU_FILAMENTS = {
    "GFA00": "Bambu PLA Basic", "GFA01": "Bambu PLA Matte", "GFA02": "Bambu PLA Metal",
    "GFA05": "Bambu PLA Silk", "GFA06": "Bambu PLA Silk+", "GFA07": "Bambu PLA Marble",
    "GFA08": "Bambu PLA Sparkle", "GFA09": "Bambu PLA Tough", "GFA11": "Bambu PLA Aero",
    "GFA12": "Bambu PLA Glow", "GFA13": "Bambu PLA Dynamic", "GFA15": "Bambu PLA Galaxy",
    "GFA16": "Bambu PLA Wood", "GFA50": "Bambu PLA-CF", "GFB00": "Bambu ABS",
    "GFB01": "Bambu ASA", "GFB02": "Bambu ASA-Aero", "GFB50": "Bambu ABS-GF",
    "GFB51": "Bambu ASA-CF", "GFB60": "PolyLite ABS", "GFB61": "PolyLite ASA",
    "GFB98": "Generic ASA", "GFB99": "Generic ABS", "GFC00": "Bambu PC",
    "GFC01": "Bambu PC FR", "GFC99": "Generic PC", "GFG00": "Bambu PETG Basic",
    "GFG01": "Bambu PETG Translucent", "GFG02": "Bambu PETG HF", "GFG50": "Bambu PETG-CF",
    "GFG60": "PolyLite PETG", "GFG96": "Generic PETG HF", "GFG97": "Generic PCTG",
    "GFG98": "Generic PETG-CF", "GFG99": "Generic PETG", "GFL00": "PolyLite PLA",
    "GFL01": "PolyTerra PLA", "GFL03": "eSUN PLA+", "GFL04": "Overture PLA",
    "GFL05": "Overture Matte PLA", "GFL06": "Fiberon PETG-ESD", "GFL50": "Fiberon PA6-CF",
    "GFL51": "Fiberon PA6-GF", "GFL52": "Fiberon PA12-CF", "GFL53": "Fiberon PA612-CF",
    "GFL54": "Fiberon PET-CF", "GFL55": "Fiberon PETG-rCF", "GFL95": "Generic PLA High Speed",
    "GFL96": "Generic PLA Silk", "GFL98": "Generic PLA-CF", "GFL99": "Generic PLA",
    "GFN03": "Bambu PA-CF", "GFN04": "Bambu PAHT-CF", "GFN05": "Bambu PA6-CF",
    "GFN06": "Bambu PPA-CF", "GFN08": "Bambu PA6-GF", "GFN96": "Generic PPA-GF",
    "GFN97": "Generic PPA-CF", "GFN98": "Generic PA-CF", "GFN99": "Generic PA",
    "GFP95": "Generic PP-GF", "GFP96": "Generic PP-CF", "GFP97": "Generic PP",
    "GFP98": "Generic PE-CF", "GFP99": "Generic PE", "GFR98": "Generic PHA",
    "GFR99": "Generic EVA", "GFS00": "Bambu Support W", "GFS01": "Bambu Support G",
    "GFS02": "Bambu Support For PLA", "GFS03": "Bambu Support For PA/PET", "GFS04": "Bambu PVA",
    "GFS05": "Bambu Support For PLA/PETG", "GFS06": "Bambu Support for ABS", "GFS97": "Generic BVOH",
    "GFS98": "Generic HIPS", "GFS99": "Generic PVA", "GFT01": "Bambu PET-CF",
    "GFT02": "Bambu PPS-CF", "GFT97": "Generic PPS", "GFT98": "Generic PPS-CF",
    "GFU00": "Bambu TPU 95A HF", "GFU01": "Bambu TPU 95A", "GFU02": "Bambu TPU for AMS",
    "GFU98": "Generic TPU for AMS", "GFU99": "Generic TPU"
}

# HMS Diagnostic Mapping
HMS_DATA = {}

def load_hms_data():
    global HMS_DATA
    try:
        # Possíveis caminhos: local, no bundle (_MEIPASS) ou pasta do script
        paths = [
            'hms_Classificado_pt-br.json',
            os.path.join(getattr(sys, '_MEIPASS', ''), 'hms_Classificado_pt-br.json'),
            os.path.join(os.path.dirname(__file__), 'hms_Classificado_pt-br.json')
        ]
        for path in paths:
            if path and os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    HMS_DATA = json.load(f)
                    log_info(f"HMS: {len(HMS_DATA.get('device_hms', {})) + len(HMS_DATA.get('device_error', {}))} códigos carregados de {path}")
                    return
    except Exception as e:
        log_error(f"Erro ao carregar HMS Data: {e}")

def get_hms_desc(code):
    """
    Retorna um dicionário com os dados de um código HMS em português.
    :param code: Código em hex (8 ou 16 caracteres)
    :return: {"desc": str, "criticidade": int, "status": str} ou None
    """
    if not HMS_DATA:
        return None
    
    # Normalizar (remover underscores se houver)
    clean_code = code.replace("_", "").upper()
    
    for cat in ['device_hms', 'device_error', 'device_info']:
        if cat in HMS_DATA:
            # 1. Tenta código completo (16 ou 8)
            if clean_code in HMS_DATA[cat]:
                entry = HMS_DATA[cat][clean_code]
                if isinstance(entry, dict) and entry:
                    keys = list(entry.keys())
                    if not keys: continue
                    desc_key = keys[0]
                    dados = entry[desc_key]
                    if isinstance(dados, dict):
                        return {"desc": desc_key, "criticidade": dados.get("criticidade", 0), "status": dados.get("status", "")}
                    return {"desc": desc_key, "criticidade": 0, "status": ""}
            
            # 2. Se for 16, tenta apenas os primeiros 8 (categoria/erro geral)
            if len(clean_code) == 16:
                short = clean_code[:8]
                if short in HMS_DATA[cat]:
                    entry = HMS_DATA[cat][short]
                    if isinstance(entry, dict) and entry:
                        keys = list(entry.keys())
                        if not keys: continue
                        desc_key = keys[0]
                        dados = entry[desc_key]
                        if isinstance(dados, dict):
                            return {"desc": desc_key, "criticidade": dados.get("criticidade", 0), "status": dados.get("status", "")}
                        return {"desc": desc_key, "criticidade": 0, "status": ""}
    return None

# Inicializar HMS
import os
load_hms_data()


def get_bambu_filament_name(idx):
    if not idx: return ""
    return BAMBU_FILAMENTS.get(idx, "Unknown")

# Base Printer Class
class BasePrinter:
    def __init__(self, config):
        self.config = config
        self.ip = config.get('ip')
        self.name = config.get('name', 'Unknown Printer')
        self.type = config.get('type')
        self.status = {
            'state': 'offline',
            'temp_nozzle': 0,
            'temp_bed': 0,
            'progress': 0,
            'filename': '',
            'remaining_time': 0,
            'layer': 0,
            'total_layers': 0,
            'finish_time': '--',
            'print_duration': 0,
            'total_duration': 0,
            'total_usage': config.get('total_usage', 0.0)
        }
        self.last_update = 0
        self.last_usage_time = time.time()
        self.last_frame = None
        self._last_snapshot_time = 0

    def connect(self):
        pass

    def update(self):
        pass

    def _reset_status(self):
        """Limpa os dados dinâmicos da impressora."""
        self.status.update({
            'state': 'off',
            'temp_nozzle': 0,
            'temp_bed': 0,
            'progress': 0,
            'filename': '',
            'remaining_time': 0,
            'layer': 0,
            'total_layers': 0,
            'finish_time': '--',
            'target_nozzle': 0,
            'target_bed': 0,
            'chamber_temp': 0,
            'target_chamber_temp': 0,
            'temp_nozzle_left': None,
            'temp_nozzle_right': None,
            'target_nozzle_left': 0,
            'target_nozzle_right': 0,
            'active_nozzle': None,
            'door_open': None,
            'fan_part': 0,
            'fan_aux': 0,
            'fan_secondary_aux': 0,
            'fan_chamber': 0,
            'ams': [],
            'hms': [],
            'wifi_signal': 0
        })
        self.last_frame = None

    def send_command(self, command, **kwargs):
        pass

    def get_snapshot(self):
        """Tenta buscar um snapshot de uma câmera genérica via camera_url."""
        url = self.config.get('camera_url', '')
        if not url: return None
        
        try:
            # Se for um link de stream mjpg-streamer, tenta converter para snapshot
            snap_url = url
            if 'action=stream' in url:
                snap_url = url.replace('action=stream', 'action=snapshot')
            
            # Usar modo stream=True para capturar apenas um frame se for um vídeo/stream infinito
            with requests.get(snap_url, timeout=3, stream=True) as resp:
                if resp.status_code == 200:
                    # Se for um JPEG direto (possui tamanho fixo pequeno), lê tudo
                    content_length = int(resp.headers.get('Content-Length', 0))
                    if 0 < content_length < 1500000: # < 1.5MB
                        return resp.content

                    # Para MJPEG Streams ou URLs sem Content-Length (ex: ESP32-CAM)
                    # Procuramos o SOI (FF D8) e o EOI (FF D9) para extrair o primeiro frame completo
                    content = b""
                    MAX_SCAN = 1024 * 1024 # Limite de 1MB para não estourar memória
                    for chunk in resp.iter_content(chunk_size=8192):
                        content += chunk
                        if b'\xff\xd8' in content:
                            # Limpa lixo antes do início da imagem
                            content = content[content.find(b'\xff\xd8'):]
                            if b'\xff\xd9' in content:
                                # Retorna exatamente o frame do SOI ao EOI
                                return content[:content.find(b'\xff\xd9') + 2]
                        if len(content) > MAX_SCAN: break
        except:
            pass
        return None

    def stop(self):
        """Para todos os serviços e threads da impressora."""
        pass

    def get_status(self):
        s = self.status.copy()
        s['id'] = self.config.get('id')
        s['name'] = self.name
        s['type'] = self.type
        s['ip'] = self.ip
        s['serial'] = self.config.get('serial', '')
        s['access_code'] = self.config.get('access_code', '')
        s['camera_url'] = self.config.get('camera_url', '')
        s['custom_camera'] = self.config.get('custom_camera', False)
        s['camera_refresh'] = self.config.get('camera_refresh', False)
        s['refresh_interval'] = self.config.get('refresh_interval', 5000)
        s['platform_token'] = self.config.get('platform_token', '')
        s['enabled'] = self.config.get('enabled', True)
        s['ignore_unknown_hms'] = self.config.get('ignore_unknown_hms', True)
        s['last_update'] = self.last_update
        return s

# Moonraker (Klipper) Implementation
class MoonrakerPrinter(BasePrinter):
    def __init__(self, config):
        super().__init__(config)
        self.current_filename = ""
        self.led_pin = "LED" 
        self._fetch_webcams()
        self._discover_objects()

    def _discover_objects(self):
        try:
            url = f"http://{self.ip}/printer/objects/list"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                objs = resp.json().get('result', {}).get('objects', [])
                # Procura por pinos de LED conhecidos
                if 'output_pin caselight' in objs: self.led_pin = "caselight"
                elif 'output_pin LED' in objs: self.led_pin = "LED"
                
                log_info(f"[{self.ip}] Moonraker descoberto: LED={self.led_pin}")
        except Exception as e:
            log_error(f"[{self.ip}] Erro ao descobrir objetos Moonraker: {e}")

    def _fetch_webcams(self):
        try:
            url = f"http://{self.ip}/server/webcams/list"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                webcams = resp.json().get('result', {}).get('webcams', [])
                if webcams:
                    cam = webcams[0]
                    stream = cam.get('stream_url', '')
                    if stream:
                        if stream.startswith('/'):
                            self.status['auto_camera_url'] = f"http://{self.ip}{stream}"
                        else:
                            self.status['auto_camera_url'] = stream
        except:
            pass

    def get_status(self):
        s = super().get_status()
        s['auto_camera_url'] = self.status.get('auto_camera_url', '')
        return s

    def _fetch_metadata(self, filename):
        if not filename:
            self.status['cover_image'] = None
            self.status['total_duration'] = 0
            return
        try:
            url = f"http://{self.ip}/server/files/metadata?filename={filename}"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                data = resp.json().get('result', {})
                
                # Total duration estimate from metadata (seconds to minutes)
                est = data.get('estimated_time', 0)
                if est > 0:
                    self.status['total_duration'] = int(est / 60)
                
                thumbs = data.get('thumbnails', [])
                if thumbs:
                    # Pick largest thumbnail
                    thumb = thumbs[-1]
                    self.status['cover_image'] = f"http://{self.ip}/server/files/gcodes/{thumb['relative_path']}"
                else:
                    self.status['cover_image'] = None
        except:
            self.status['cover_image'] = None

    def update(self):
        # Incrementar horas de uso se estiver imprimindo
        now = time.time()
        if self.status.get('state', '').lower() in ['printing', 'running']:
            delta = now - self.last_usage_time
            self.status['total_usage'] = self.status.get('total_usage', 0) + (max(0, delta) / 3600.0)
        self.last_usage_time = now

        try:
            url = f"http://{self.ip}/printer/objects/query?print_stats&extruder&heater_bed&display_status&fan&toolhead&virtual_sdcard&output_pin%20{self.led_pin}&temperature_sensor%20mcu_temp&temperature_sensor%20chamber_temp&system_stats"
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                res = data.get('result', {}).get('status', {})
                
                # Update status
                if 'print_stats' in res:
                    state = res['print_stats'].get('state', 'unknown')
                    # Map 'standby' to 'idle' for UI consistency
                    self.status['state'] = 'idle' if state == 'standby' else state
                    
                    filename = res['print_stats'].get('filename', '')
                    if filename != self.current_filename:
                        self.current_filename = filename
                        self._fetch_metadata(filename)
                    
                    self.status['filename'] = filename
                    self.status['print_duration'] = res['print_stats'].get('print_duration', 0)
                
                if 'extruder' in res:
                    self.status['temp_nozzle'] = res['extruder'].get('temperature', 0)
                    self.status['target_nozzle'] = res['extruder'].get('target', 0)
                
                if 'heater_bed' in res:
                    self.status['temp_bed'] = res['heater_bed'].get('temperature', 0)
                    self.status['target_bed'] = res['heater_bed'].get('target', 0)
                
                if 'display_status' in res:
                    self.status['progress'] = res['display_status'].get('progress', 0) * 100
                
                # Fetch LED value
                lp = f'output_pin {self.led_pin}'
                if lp in res:
                    self.status['led_val'] = int(res[lp].get('value', 0) * 100)
                
                # Fetch Fan part value
                if 'fan' in res:
                    self.status['fan_val'] = int(res['fan'].get('speed', 0) * 100)
                
                if 'temperature_sensor chamber_temp' in res:
                    self.status['chamber_temp'] = res['temperature_sensor chamber_temp'].get('temperature', 0)
                
                # Remaining time and Finish time from virtual_sdcard or print_stats
                rem_time = 0
                if 'virtual_sdcard' in res:
                    # Klipper approach: (1 - progress) * total_duration / progress (very rough)
                    # Better to use Moonraker's estimation if available
                    pass
                
                if 'print_stats' in res:
                    # Some Moonraker versions provide it here
                    stats = res['print_stats']
                    # print_duration is elapsed. We need remaining.
                    # Usually we get it from display_status if available
                    pass
                
                if 'display_status' in res and 'progress' in res['display_status']:
                    # We can't always get exact remaining from simple query, 
                    # but if we have progress and elapsed, we can estimate
                    prog = res['display_status'].get('progress', 0)
                    elapsed = res['print_stats'].get('print_duration', 0) if 'print_stats' in res else 0
                    if prog > 0 and prog < 1:
                        total_est = elapsed / prog
                        rem_time = (total_est - elapsed) / 60 # minutes
                        self.status['remaining_time'] = int(rem_time)
                        
                        # Use file estimate if available and larger, otherwise use calculated total
                        calculated_total = int(total_est / 60)
                        file_est = self.status.get('total_duration', 0)
                        self.status['total_duration'] = max(calculated_total, file_est)
                        
                        self.status['print_duration'] = int(elapsed / 60) # minutes
                        finish_dt = datetime.now() + timedelta(minutes=rem_time)
                        self.status['finish_time'] = finish_dt.strftime("%H:%M")
                    elif prog >= 1:
                        self.status['remaining_time'] = 0
                        self.status['total_duration'] = self.status.get('print_duration', 0)
                        self.status['finish_time'] = '--'
                
                
                self.last_update = time.time()
                return True
            else:
                self.status['state'] = 'offline'
        except Exception as e:
            log_debug(f"Moonraker update failed for {self.ip}: {e}")
            self.status['state'] = 'offline'
        return False

    def send_command(self, command, **kwargs):
        try:
            if command == 'pause':
                requests.post(f"http://{self.ip}/printer/print/pause", timeout=3)
            elif command == 'resume':
                requests.post(f"http://{self.ip}/printer/print/resume", timeout=3)
            elif command == 'stop':
                requests.post(f"http://{self.ip}/printer/print/cancel", timeout=3)
            elif command == 'home':
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': 'G28'}, timeout=3)
            elif command == 'motors_off':
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': 'M84'}, timeout=3)
            elif command == 'gcode':
                gcode = kwargs.get('gcode', '')
                if gcode:
                    requests.post(f"http://{self.ip}/printer/gcode/script",
                        json={'script': gcode}, timeout=3)
            elif command == 'fan':
                val = int(kwargs.get('val', 0))
                self.status['fan_val'] = val
                pwm = int(val / 100 * 255)
                # Part fan is standard M106 P0
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'M106 P0 S{pwm}'}, timeout=3)
            elif command == 'led':
                val = int(kwargs.get('val', 0))
                self.status['led_val'] = val
                fval = val / 100.0
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'SET_PIN PIN={self.led_pin} VALUE={fval:.2f}'}, timeout=3)
                # Se for M355 compatível, envia também apenas para garantir
                if self.led_pin == "LED":
                    pwm = int(val / 100 * 255)
                    requests.post(f"http://{self.ip}/printer/gcode/script",
                        json={'script': f'M355 S{1 if val > 0 else 0} P{pwm}'}, timeout=3)
            elif command == 'reboot':
                requests.post(f"http://{self.ip}/machine/reboot", timeout=3)
        except Exception as e:
            log_error(f"Moonraker command error: {e}")

    def get_snapshot(self):
        try:
            # Try to determine snapshot URL
            base_ip = self.ip.split(':')[0]
            # If camera_url is in config, use it but replace action=stream with action=snapshot
            cam_url = self.config.get('camera_url', '')
            
            snap_url = ""
            if 'action=stream' in cam_url:
                snap_url = cam_url.replace('action=stream', 'action=snapshot')
            elif cam_url:
                # If explicit URL but not mjpg-streamer standard, try as is (unlikely for stream link)
                snap_url = cam_url
            else:
                # Default guess for K1/Moonraker
                # K1 usually on port 4409 for camera? Config says ip:4409
                if ':' in self.ip:
                    snap_url = f"http://{self.ip}/webcam/?action=snapshot"
                else:
                    snap_url = f"http://{self.ip}:4409/webcam/?action=snapshot"

            resp = requests.get(snap_url, timeout=2)
            if resp.status_code == 200:
                return resp.content
        except Exception as e:
            # log_debug(f"Snapshot failed: {e}")
            pass
        return None

    def stop(self):
        self._reset_status()

# Elegoo (Saturn 3 Ultra) Implementation - UDP
class ElegooPrinter(BasePrinter):
    def __init__(self, config):
        super().__init__(config)
        self.port = config.get('port', 3000)
        # Resin printers don't have nozzle/bed temperatures
        self.status.pop('temp_nozzle', None)
        self.status.pop('temp_bed', None)

    def _send_command(self, message):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.5) # Aumentar ligeiramente
            sock.sendto(message.encode(), (self.ip, self.port))
            data, _ = sock.recvfrom(4096)
            return json.loads(data.decode())
        except socket.timeout:
            # log_debug(f"Elegoo timeout: {self.ip}")
            return None
        except Exception as e:
            log_debug(f"Elegoo error: {e}")
            return None
        finally:
            if sock:
                try: sock.close()
                except: pass

    def update(self):
        # Incrementar horas de uso se estiver imprimindo
        now = time.time()
        if self.status.get('state', '').lower() in ['printing', 'running']:
            delta = now - self.last_usage_time
            self.status['total_usage'] = self.status.get('total_usage', 0) + (max(0, delta) / 3600.0)
        self.last_usage_time = now

        data = self._send_command("M99999")
        if data:
            # Structure from user's working example:
            # response.get("Data", {}).get("Status", {}).get("PrintInfo", {})
            wrapper = data.get("Data", {})
            status = wrapper.get("Status", {})
            info = status.get("PrintInfo", {})

            # Status translation
            status_code = status.get("CurrentStatus", -1)
            status_map = {0: "Idle", 1: "Printing", 2: "Paused", 3: "Error"}
            self.status['state'] = status_map.get(status_code, "Unknown").lower()
            
            if info:
                self.status['layer'] = info.get("CurrentLayer", 0)
                self.status['total_layers'] = info.get("TotalLayer", 0)
                self.status['filename'] = info.get("Filename", "")
                
                # Progress calculation
                if self.status['total_layers'] > 0:
                    self.status['progress'] = (self.status['layer'] / self.status['total_layers']) * 100
                else:
                    self.status['progress'] = 0
                
                # Time calculation (ticks to minutes for fmtEta compatibility)
                current_ticks = info.get("CurrentTicks", 0)
                total_ticks = info.get("TotalTicks", 0)
                if total_ticks > current_ticks:
                    remaining_ticks = total_ticks - current_ticks
                    # remaining_time in minutes for fmtEta
                    self.status['remaining_time'] = (remaining_ticks // 1000) // 60
                    
                    # Estimate finish time string (HH:mm)
                    remaining_seconds = remaining_ticks / 1000
                    finish_dt = datetime.now() + timedelta(seconds=remaining_seconds)
                    self.status['finish_time'] = finish_dt.strftime("%H:%M")
                else:
                    self.status['remaining_time'] = 0
                    self.status['finish_time'] = '--'
            
            self.last_update = time.time()
            return True
        else:
            self.status['state'] = 'offline'
            return False

    def send_command(self, command, **kwargs):
        if command == 'pause':
            self._send_command("M25")
        elif command == 'resume':
            self._send_command("M24")
        elif command == 'stop':
            self._send_command("M33")

    def stop(self):
        self._reset_status()

class BambuCameraThread(threading.Thread):
    def __init__(self, ip, access_code, callback):
        super().__init__(daemon=True)
        self.ip = ip
        self.access_code = access_code
        self.callback = callback
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        self.setName(f"BambuCamera-{self.ip}")
        log_info(f"[{self.ip}] Iniciando thread da câmera (Bambu/X1C)...")
        
        username = 'bblp'
        port = 6000
        auth_data = bytearray()
        auth_data += struct.pack("<I", 0x40)
        auth_data += struct.pack("<I", 0x3000)
        auth_data += struct.pack("<I", 0)
        auth_data += struct.pack("<I", 0)
        for c in username: auth_data += struct.pack("<c", c.encode('ascii'))
        for i in range(32 - len(username)): auth_data += struct.pack("<x")
        for c in self.access_code: auth_data += struct.pack("<c", c.encode('ascii'))
        for i in range(32 - len(self.access_code)): auth_data += struct.pack("<x")

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT

        # Payload format for each image is:
        # 16 byte header:
        #   Bytes 0:3   = little endian payload size for the jpeg image (does not include this header).
        #   Bytes 4:7   = 0x00000000
        #   Bytes 8:11  = 0x00000001
        #   Bytes 12:15 = 0x00000000
        # These first 16 bytes are always delivered by themselves.
        
        # A1/A1 Mini can be very sensitive to reading speed.
        
        while not self._stop_event.is_set():
            try:
                # SSL Context as per example (optimized for Bambu)
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
                ctx.set_ciphers('DEFAULT@SECLEVEL=1:AES128-SHA')
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT

                with socket.create_connection((self.ip, port), timeout=10) as sock:
                    sslSock = ctx.wrap_socket(sock, server_hostname=self.ip)
                    sslSock.write(auth_data)
                    sslSock.setblocking(False)
                    
                    img = None
                    payload_size = 0
                    
                    while not self._stop_event.is_set():
                        try:
                            # Use 8192 for potentially faster draining of A1/P1 buffer
                            dr = sslSock.recv(8192)
                        except ssl.SSLWantReadError:
                            # 1s (from example) might be too slow for A1 if the buffer fills up.
                            # Using 0.1s for better responsiveness.
                            if self._stop_event.wait(0.1): break
                            continue
                        except:
                            break

                        if not dr:
                            break

                        if img is not None:
                            img += dr
                            if len(img) > payload_size:
                                # Data exceeded expected size, reset sync
                                img = None
                            elif len(img) == payload_size:
                                # JPEG check: A1 might use different APPn segments than X1. 
                                # Strict FF D8 FF E0 check might fail on some A1 frames.
                                if img.startswith(b'\xff\xd8') and img.endswith(b'\xff\xd9'):
                                    self.callback(bytes(img))
                                # Reset for next header
                                img = None
                        elif len(dr) == 16:
                            # Validated Header check (more robust than just length 16)
                            # Header usually looks like [size, 0, 1, 0] in 32-bit units
                            if dr[4:16] == b'\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00':
                                img = bytearray()
                                payload_size = int.from_bytes(dr[0:3], byteorder='little')
                            else:
                                # Not a valid header, wait for next chunk
                                img = None
                        else:
                            # Not a header and we weren't expecting data. Reset and wait.
                            img = None

            except Exception as e:
                if not self._stop_event.is_set():
                    log_debug(f"[{self.ip}] Câmera Bambu (A1/X1): {e}")
                    if self._stop_event.wait(5): break

    def stop(self):
        self._stop_event.set()
        # Não damos join aqui para não travar o loop principal, 
        # mas a thread é daemon então ok.

class BambuRTSPProxyThread(threading.Thread):
    def __init__(self, target_host, target_port):
        super().__init__(daemon=True)
        self.target_host = target_host
        self.target_port = target_port
        self.local_port = 0
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.bind(('127.0.0.1', 0))
        self.local_port = self.server_sock.getsockname()[1]
        self.server_sock.listen(1)
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            try:
                self.server_sock.settimeout(1.0)
                client_sock, addr = self.server_sock.accept()
                threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                break

    def stop(self):
        self._stop_event.set()
        try:
            self.server_sock.close()
        except: pass

    def _handle_client(self, client_sock):
        try:
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            target_sock = socket.create_connection((self.target_host, self.target_port), timeout=10.0)
            tls_sock = ssl_ctx.wrap_socket(target_sock, server_hostname=self.target_host)
            
            proxy_url = f"rtsp://127.0.0.1:{self.local_port}".encode()
            real_url = f"rtsps://{self.target_host}:{self.target_port}".encode()

            def forward(src, dst, rewrite=False):
                try:
                    while not self._stop_event.is_set():
                        data = src.recv(65536)
                        if not data: break
                        if rewrite and b" RTSP/1.0" in data:
                            lines = data.split(b"\r\n")
                            for i, line in enumerate(lines):
                                if line.endswith(b" RTSP/1.0"):
                                    lines[i] = line.replace(proxy_url, real_url)
                                    break
                            data = b"\r\n".join(lines)
                        dst.sendall(data)
                except: pass
                finally:
                    try: dst.close()
                    except: pass
                    try: src.close()
                    except: pass

            t1 = threading.Thread(target=forward, args=(client_sock, tls_sock, True), daemon=True)
            t2 = threading.Thread(target=forward, args=(tls_sock, client_sock, False), daemon=True)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
        except Exception as e:
            try: client_sock.close()
            except: pass

class BambuX1CCameraThread(threading.Thread):
    def __init__(self, ip, access_code, callback):
        super().__init__(daemon=True)
        self.ip = ip
        self.access_code = access_code
        self.callback = callback
        self._stop_event = threading.Event()
        self.proxy = None
        self.ffmpeg_proc = None

    def stop(self):
        self._stop_event.set()
        if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            self.ffmpeg_proc.terminate()
            try:
                self.ffmpeg_proc.wait(timeout=2)
            except:
                self.ffmpeg_proc.kill()
        if self.proxy:
            self.proxy.stop()

    def run(self):
        ffmpeg_path = get_ffmpeg_path()
        if not ffmpeg_path:
            log_error("FFmpeg not found. Cannot start X1C camera via RTSP.")
            return
            
        self.proxy = BambuRTSPProxyThread(self.ip, 322)
        self.proxy.start()
        
        camera_url = f"rtsp://bblp:{self.access_code}@127.0.0.1:{self.proxy.local_port}/streaming/live/1"
        
        cmd = [
            ffmpeg_path,
            "-y",
            "-rtsp_transport", "tcp",
            "-rtsp_flags", "prefer_tcp",
            "-i", camera_url,
            "-frames:v", "1",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-q:v", "2",
            "-",
        ]
        
        spawn_kwargs = {}
        if sys.platform == "win32":
            spawn_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
        log_info(f"[{self.ip}] Iniciando thread da câmera X1C (Modo Snapshot/FFmpeg)...")
        
        while not self._stop_event.is_set():
            try:
                self.ffmpeg_proc = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    **spawn_kwargs
                )
                FFMPEG_PROCESSES.append(self.ffmpeg_proc)
                
                # Aguarda até no máximo 15s para baixar o frame e sair
                try:
                    stdout, stderr = self.ffmpeg_proc.communicate(timeout=15)
                    if self.ffmpeg_proc.returncode == 0 and stdout and len(stdout) >= 100:
                        self.callback(stdout)
                    else:
                        err_text = ""
                        if stderr:
                            err_text = stderr.decode(errors="replace")
                        log_debug(f"[{self.ip}] FFmpeg retornou {self.ffmpeg_proc.returncode}. Erro: {err_text[:200]}")
                except subprocess.TimeoutExpired:
                    if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
                        self.ffmpeg_proc.kill()
                    log_debug(f"[{self.ip}] Timeout capturando frame X1C")
                finally:
                    if self.ffmpeg_proc in FFMPEG_PROCESSES:
                        try: FFMPEG_PROCESSES.remove(self.ffmpeg_proc)
                        except: pass
                        
            except Exception as e:
                log_debug(f"X1C ffmpeg error: {e}")
                
            if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
                self.ffmpeg_proc.terminate()
                
            # Tempo de espera entre os frames (para não sobrecarregar)
            if self._stop_event.wait(0.5):
                break

# Helper for Implicit FTP TLS (used by Bambu Lab)
class ImplicitFTP_TLS(ftplib.FTP_TLS):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            session = self.sock.session
            if isinstance(self.sock, ssl.SSLSocket):
                session = self.sock.session
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=session)
        return conn, size

# Bambu Lab Implementation - MQTT
class BambuPrinter(BasePrinter):
    def __init__(self, config):
        super().__init__(config)
        self.serial = config.get('serial')
        self.access_code = config.get('access_code')
        self.client = None
        self.connected_flag = False
        self.lock = threading.Lock()
        self.cam_thread = None
        self.last_frame = None
        self.metadata_thread = None
        self.current_filename = ""
        
        # New status fields
        self.status.update({
            'target_nozzle': 0,
            'target_bed': 0,
            'chamber_temp': 0,
            'target_chamber_temp': 0,    # câmara aquecida (H2D/H2C/X1E)
            'fan_part': 0,
            'fan_aux': 0,
            'fan_chamber': 0,
            'fan_secondary_aux': 0,      # ventilador auxiliar secundário (P2S/X2D)
            'ams': [],
            'hms': [],
            'speed_level': 2, # Normal
            'wifi_signal': 0,
            'task_name': '',
            'print_weight': 0,
            'active_tray_name': 'None',
            'active_tray_uuid': '',
            'firmware_update': {'current': '', 'latest': '', 'available': False},
            'print_error': {'code': 0, 'message': ''},
            'started_at': None,
            # --- Dual Nozzle (H2D, H2C, X2D) ---
            'device_model': '',           # detectado via get_version
            'temp_nozzle_right': None,       # bico id=0 (direito)
            'target_nozzle_right': 0,
            'temp_nozzle_left': None,        # bico id=1 (esquerdo)
            'target_nozzle_left': 0,
            'active_nozzle': 0,           # 0=direito, 1=esquerdo
            'nozzle_diameter_right': None,
            'nozzle_diameter_left': None,
            'nozzle_type_right': None,
            'nozzle_type_left': None,
            # --- Door Sensor ---
            'door_open': False,
        })
        # total_usage já está no BasePrinter.status
        self.start_time = None
        self.print_start_time = None # Para cronômetro de impressão local

    def connect(self):
        # Conexão em thread para não travar a inicialização do server
        if not self.config.get('enabled', True): return
        if self.client: return
        thread = threading.Thread(target=self._do_connect, daemon=True)
        thread.start()

    def _do_connect(self):
        log_info(f"[{self.ip}] Conectando ao MQTT e Câmera...")
        self.client = mqtt.Client(client_id=f"aditiva-{int(time.time())}")
        self.client.username_pw_set("bblp", self.access_code)
        
        # Contexto SSL - Igual ao exemplo que funciona
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.set_ciphers('DEFAULT@SECLEVEL=1:AES128-SHA')
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self.client.tls_set_context(context)
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        try:
            self.client.connect(self.ip, 8883, 10) 
            self.client.loop_start()
            
            # Aguardar o MQTT estabilizar antes de abrir a câmera (importante para X1C)
            time.sleep(2)
            
            if not self.cam_thread:
                # O X1C usa RTSP na porta 322 (prefixo de série começa com 00M, 00W, 00E)
                # P1 / A1 usam porta 6000
                # Modelos que usam câmera RTSP na porta 322 (via FFmpeg):
                # X1C/X1E = 00M, 00W, 00E | H2D = 094
                is_x1c = self.serial and self.serial.startswith(("00M", "00W", "00E", "094"))

                if is_x1c:
                    if get_ffmpeg_path():
                        self.cam_thread = BambuX1CCameraThread(self.ip, self.access_code, self.on_frame)
                        self.cam_thread.start()
                    else:
                        log_error(f"[{self.ip}] ALERTA: FFmpeg não instalado no Windows! A câmera da X1C não pode ser iniciada.")
                else:
                    self.cam_thread = BambuCameraThread(self.ip, self.access_code, self.on_frame)
                    self.cam_thread.start()
        except Exception as e:
            log_error(f"[{self.ip}] Falha na conexão MQTT: {e}")
            self.status['state'] = 'offline'

    def stop(self):
        log_info(f"[{self.ip}] Parando serviços Bambu (Threads e MQTT)...")
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except: pass
        if self.cam_thread:
            try:
                self.cam_thread.stop()
            except: pass
        self.connected_flag = False
        self._reset_status()
        self.status['state'] = 'off'
        

    def on_frame(self, frame):
        self.last_frame = frame

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected_flag = True
            topic = f"device/{self.serial}/report"
            client.subscribe(topic)
            self.request_push()

    def request_push(self):
        if not self.connected_flag: return
        msg_push = {"pushing": {"sequence_id": "0", "command": "pushall"}}
        self.client.publish(f"device/{self.serial}/request", json.dumps(msg_push))
        
        # Também pedir infos (versão, usage_hours etc)
        msg_info = {"info": {"sequence_id": "0", "command": "get_version"}}
        self.client.publish(f"device/{self.serial}/request", json.dumps(msg_info))

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self.parse_bambu_json(payload)
            self.last_update = time.time()
        except Exception as e:
            log_error(f"Error parsing Bambu msg: {e}")

    def parse_bambu_json(self, data):
        with self.lock:
            # Pegar dados de print (pode estar no topo ou dentro de data)
            p = data.get('print', {})
            is_a1_series = self.serial and self.serial.startswith(("030", "039"))
            
            if p:

                curr_state = p.get('gcode_state', '').lower() or self.status.get('state', '').lower()
                if 'gcode_state' in p:
                    new_state = p['gcode_state'].lower()
                    prev_state = self.status.get('state', '').lower()
                    
                    if new_state in ['printing', 'running'] and prev_state not in ['printing', 'running']:
                        # Resetar thumbnail ao começar impressão nova ou reimpressão
                        self.status['cover_image'] = None
                        self.print_start_time = time.time()
                        self.status['started_at'] = datetime.now().strftime("%H:%M")
                        
                    self.status['state'] = new_state
                if 'mc_percent' in p:
                    self.status['progress'] = p['mc_percent']
                if 'mc_remaining_time' in p:
                    self.status['remaining_time'] = p['mc_remaining_time']
                    dt = datetime.now() + timedelta(minutes=p['mc_remaining_time'])
                    self.status['finish_time'] = dt.strftime("%H:%M")
                # --- Temperaturas (Novo formato H2D: device.* ; Legado: campos flat) ---
                device = p.get('device', {})

                # Bed temp — novo formato (low word = atual, high word = alvo)
                bed_raw = device.get('bed', {}).get('info', {}).get('temp')
                if bed_raw is not None:
                    self.status['temp_bed'] = bed_raw & 0xFFFF
                    self.status['target_bed'] = (bed_raw >> 16) & 0xFFFF
                else:
                    if 'bed_temper' in p:
                        self.status['temp_bed'] = p['bed_temper']
                    if 'bed_target_temper' in p:
                        self.status['target_bed'] = p['bed_target_temper']

                # Chamber temp + target — novo formato (ctc)
                # A1/A1 Mini não possuem câmara fechada nem sensor de porta
                if not is_a1_series:
                    ctc_raw = device.get('ctc', {}).get('info', {}).get('temp')
                    if ctc_raw is None:
                        ctc_raw = data.get('device', {}).get('ctc', {}).get('info', {}).get('temp')
                    
                    if ctc_raw is not None:
                        self.status['chamber_temp'] = ctc_raw & 0xFFFF
                        self.status['target_chamber_temp'] = (ctc_raw >> 16) & 0xFFFF
                    elif 'chamber_temper' in p:
                        self.status['chamber_temp'] = round(p['chamber_temper'])
                    elif 'chamber_temper' in data:
                        self.status['chamber_temp'] = round(data['chamber_temper'])
                else:
                    self.status['chamber_temp'] = None
                    self.status['door_open'] = None

                # Dual Nozzle temperatures (H2D: device.extruder.info[{id,temp}])
                extruder_block = device.get('extruder', {})
                extruder_info = extruder_block.get('info')
                if extruder_info:
                    extruder_state = extruder_block.get('state', 0)
                    # bits 4-7 = extrusor ativo (0=direito, 1=esquerdo)
                    active_nozzle = (extruder_state >> 4) & 0xF
                    self.status['active_nozzle'] = active_nozzle
                    for entry in extruder_info:
                        nid = entry.get('id')
                        temp_raw = entry.get('temp')
                        if temp_raw is not None:
                            t_cur = temp_raw & 0xFFFF
                            t_tgt = (temp_raw >> 16) & 0xFFFF
                            if nid == 0:
                                self.status['temp_nozzle_right'] = t_cur
                                self.status['target_nozzle_right'] = t_tgt
                            elif nid == 1:
                                self.status['temp_nozzle_left'] = t_cur
                                self.status['target_nozzle_left'] = t_tgt
                    # Compat: temp_nozzle = bico ativo
                    if active_nozzle == 1:
                        self.status['temp_nozzle'] = self.status['temp_nozzle_left']
                        self.status['target_nozzle'] = self.status['target_nozzle_left']
                    else:
                        self.status['temp_nozzle'] = self.status['temp_nozzle_right']
                        self.status['target_nozzle'] = self.status['target_nozzle_right']
                else:
                    # Legado: campos flat (X1C, A1, P1S...)
                    if 'nozzle_temper' in p:
                        self.status['temp_nozzle'] = p['nozzle_temper']
                    if 'nozzle_target_temper' in p:
                        self.status['target_nozzle'] = p['nozzle_target_temper']

                # Nozzle diameter e tipo — novo formato (device.nozzle.info[])
                nozzle_info = device.get('nozzle', {}).get('info')
                if isinstance(nozzle_info, list):
                    for entry in nozzle_info:
                        nid = entry.get('id')
                        if nid == 0:
                            self.status['nozzle_diameter_right'] = entry.get('diameter')
                            self.status['nozzle_type_right'] = entry.get('type')
                        elif nid == 1:
                            self.status['nozzle_diameter_left'] = entry.get('diameter')
                            self.status['nozzle_type_left'] = entry.get('type')
                elif 'nozzle_diameter' in p:
                    self.status['nozzle_diameter_right'] = p['nozzle_diameter']
                    self.status['nozzle_type_right'] = p.get('nozzle_type')

                if 'layer_num' in p:
                    self.status['layer'] = p['layer_num']
                if 'total_layer_num' in p:
                    self.status['total_layers'] = p['total_layer_num']

                # Door sensor — X1/X1C via home_flag, H2D/H2C/P2S via 'stat' hex
                home_flag = p.get('home_flag')
                if home_flag is not None:
                    self.status['door_open'] = bool(home_flag & 0x00800000)
                stat_hex = p.get('stat')
                if stat_hex:
                    try:
                        self.status['door_open'] = bool(int(stat_hex, 16) & 0x00800000)
                    except: pass

                # Ventilador auxiliar secundário (P2S/X2D — device.airduct.parts id=160)
                airduct_parts = device.get('airduct', {}).get('parts', [])
                for part in airduct_parts:
                    if part.get('id') == 160:
                        self.status['fan_secondary_aux'] = round((int(part.get('value', 0)) / 15.0) * 100)

                # Gerenciamento de Tarefa (Nome do Arquivo e Thumbnail)
                new_file = p.get('subtask_name', '')
                prev_state = self.status.get('state', '').lower()
                
                # Se estiver em repouso (idle, ready, success, off) e sem arquivo ativo vindo no MQTT
                # Ou se o campo subtask_name veio vazio explicitamente
                is_idle = curr_state in ['idle', 'ready', 'success', 'finish', 'off']
                
                # Resetar metadados APENAS se a impressora estiver em repouso e não houver um novo arquivo vindo no MQTT
                if is_idle and not new_file:
                    if self.current_filename:
                        log_info(f"[{self.ip}] Impressão finalizada/cancelada. Limpando metadados.")
                        self.current_filename = ""
                        self.status['filename'] = ""
                        self.status['task_name'] = ""
                        self.status['cover_image'] = None
                        self.status['total_duration'] = 0
                        self.status['print_duration'] = 0
                        self.status['started_at'] = None
                        self.status['finish_time'] = None
                        self.status['layer'] = 0
                        self.status['total_layers'] = 0
                        self.status['remaining_time'] = 0
                        self.print_start_time = None
                
                elif new_file:
                    # Detectar reinício de impressão do mesmo arquivo (progresso voltou a zero ou mudou significativamente)
                    progress_reset = (p.get('mc_percent', 0) < self.status.get('progress', 0) - 5) and (curr_state in ['printing', 'running'])
                    
                    # Forçar atualização se o arquivo mudar OU se houver um reset de progresso OU se começar a imprimir vindo de outro estado
                    force_update = (new_file != self.current_filename) or progress_reset or (curr_state in ['printing', 'running'] and prev_state not in ['printing', 'running'])
                    
                    if force_update:
                        log_info(f"[{self.ip}] Nova tarefa detectada: {new_file} (ForceUpdate={force_update}, ProgressReset={progress_reset})")
                        self.current_filename = new_file
                        self.status['filename'] = new_file
                        self.status['task_name'] = new_file.replace('.gcode', '').replace('.3mf', '')
                        # Resetar metadata p/ nova task
                        self.status['cover_image'] = None
                        self.status['print_weight'] = 0
                        self.status['print_duration'] = 0
                        self.status['total_duration'] = 0
                        self.print_start_time = time.time() # Reset local timer
                        # Tentar buscar metadata via FTP
                        self._start_metadata_fetch(new_file)
                if curr_state in ['printing', 'running']:
                    if not self.print_start_time:
                        self.print_start_time = time.time()
                    # Tempo decorrido local (fallback) em minutos
                    local_elapsed = int((time.time() - self.print_start_time) / 60)
                    
                    # Tenta pegar tempo decorrido oficial da impressora
                    elapsed = p.get('mc_elapsed_time', 0)
                    if not elapsed and 'mc_print_duration' in p:
                         elapsed = p['mc_print_duration']
                    
                    # Usa o maior valor disponível para evitar quedas no cronômetro
                    self.status['print_duration'] = max(local_elapsed, elapsed)
                else:
                    self.print_start_time = None
                    self.status['print_duration'] = 0
                
                if 'mc_remaining_time' in p:
                    rem = p['mc_remaining_time']
                    self.status['remaining_time'] = rem
                    
                    # total_duration: maior entre (estimado do arquivo) e (decorrido + restante)
                    file_est = self.status.get('total_duration', 0)
                    calculated = self.status.get('print_duration', 0) + rem
                    self.status['total_duration'] = max(file_est, calculated)
                    
                    dt = datetime.now() + timedelta(minutes=rem)
                    self.status['finish_time'] = dt.strftime("%H:%M")
                    self.status['fan_part'] = round((int(p['cooling_fan_speed']) / 15.0) * 100)
                if 'big_fan1_speed' in p:
                    self.status['fan_aux'] = round((int(p['big_fan1_speed']) / 15.0) * 100)
                if 'big_fan2_speed' in p:
                    self.status['fan_chamber'] = round((int(p['big_fan2_speed']) / 15.0) * 100)
                if 'spd_lvl' in p:
                    self.status['speed_level'] = p['spd_lvl']
                if 'wifi_signal' in p:
                    try:
                        self.status['wifi_signal'] = int(p['wifi_signal'].replace('dBm', ''))
                    except: pass
                if 'hms' in p:
                    processed_hms = []
                    for h in p['hms']:
                        if isinstance(h, dict):
                            attr = h.get('attr', 0)
                            code = h.get('code', 0)
                            # Código de 16 dígitos para busca (sem underscores)
                            hms_code_lookup = f'{int(attr / 0x10000):04X}{attr & 0xFFFF:04X}{int(code / 0x10000):04X}{code & 0xFFFF:04X}'
                            # Código formatado para exibição
                            hms_code_display = f'{int(attr / 0x10000):04X}_{attr & 0xFFFF:04X}_{int(code / 0x10000):04X}_{code & 0xFFFF:04X}'
                            
                            hms_info = get_hms_desc(hms_code_lookup)
                            
                            # Filtro de erros desconhecidos/não documentados
                            ignore = self.config.get('ignore_unknown_hms', True)
                            if ignore and (not hms_info or not hms_info.get("desc")):
                                continue # Ignora se não existir ou se a descrição for vazia

                            if hms_info:
                                desc = hms_info.get("desc", "")
                                crit = hms_info.get("criticidade", 0)
                                status_name = hms_info.get("status", "")
                            else:
                                desc = ""
                                crit = 0
                                status_name = ""

                            msg = f"Atenção: HMS Code {hms_code_display} - {desc}" if desc else f"Atenção: HMS Code {hms_code_display}"
                            
                            processed_hms.append({
                                'attr': attr,
                                'code': code,
                                'hms_code': hms_code_display,
                                'description': desc,
                                'message': msg,
                                'criticidade': crit,
                                'status': status_name
                            })
                    self.status['hms'] = processed_hms
                
                # Print Error e HMS handling
                if 'print_error' in p:
                    err_code = p['print_error']
                    if err_code != 0:
                        hex_err = f"{err_code:08X}"
                        hms_info = get_hms_desc(hex_err)
                        if hms_info:
                            desc = hms_info.get("desc", "")
                            crit = hms_info.get("criticidade", 0)
                            status_name = hms_info.get("status", "")
                        else:
                            desc = ""
                            crit = 0
                            status_name = ""
                        
                        # Filtro de erros desconhecidos para print_error também
                        ignore = self.config.get('ignore_unknown_hms', True)
                        if ignore and (not hms_info or not hms_info.get("desc")):
                            self.status['print_error'] = None
                        else:
                            self.status['print_error'] = {
                                'code': err_code,
                                'message': f"Erro {hex_err} - {desc}" if desc else f"Erro {hex_err}",
                                'criticidade': crit,
                                'status': status_name
                            }
                    else:
                        self.status['print_error'] = None
            # AMS e VT Tray (Carretel Externo)
            # Podem estar no topo ou dentro de 'print'
            ams_data = data.get('ams') or p.get('ams', {})
            vt_data = data.get('vt_tray') or p.get('vt_tray', {})
            
            # Determinar ams/tray ativos
            active_ams = -1
            active_tray = -1
            tray_now = ams_data.get('tray_now') or p.get('tray_now')
            if tray_now is not None:
                try:
                    tn = int(tray_now)
                    if tn == 254: # Externo
                        active_ams = 254
                        active_tray = 0
                    elif tn < 254:
                        active_ams = tn >> 2
                        active_tray = tn & 0x03
                except: pass
            
            # Sobrescrever se houver info mais específica no print (comum em Full Report)
            if 'mc_ams_index' in p: active_ams = p['mc_ams_index']
            if 'mc_tray_index' in p: active_tray = p['mc_tray_index']

            trays = []
            
            # 1. Processar Unidades AMS
            for unit in ams_data.get('ams', []):
                unit_id = int(unit.get('id', 0))
                # humidity_index (1-5) e humidity_raw (porcentagem)
                h_index = int(unit.get('humidity', 0))
                h_pct = int(unit.get('humidity_raw', 0))
                ams_temp = float(unit.get('temp', 0))
                
                for t in unit.get('tray', []):
                    tray_id = int(t.get('id', 0))
                    is_active = (unit_id == active_ams and tray_id == active_tray)
                    
                    f_type = t.get('tray_type', '')
                    f_color = t.get('tray_color', 'FFFFFF')
                    if not f_color.startswith('#'): f_color = '#' + f_color
                    f_brand = t.get('tray_sub_brands', '')
                    f_remain = t.get('remain', -1)
                    idx = t.get('tray_info_idx', '')
                    f_uuid = t.get('tray_uuid', '')
                    
                    # Um slot é considerado vazio se não tiver tipo nem idx
                    is_empty = not f_type and not idx
                    
                    # Identificar nome amigável
                    f_name = get_bambu_filament_name(idx)
                    if f_name == "Unknown" and f_brand:
                        f_name = f"{f_brand} {f_type}".strip()
                    elif f_name == "Unknown":
                        f_name = f_type or "Desconhecido"

                    tray_data = {
                        'ams': unit_id,
                        'id': tray_id,
                        'type': f_type,
                        'brand': f_brand,
                        'name': f_name,
                        'color': f_color,
                        'remain': f_remain,
                        'uuid': f_uuid,
                        'active': is_active,
                        'empty': is_empty
                    }
                    
                    if is_a1_series:
                        # AMS Lite não tem sensores de umidade/temp - não transmitir nada
                        tray_data['humidity'] = 'N/A'
                    else:
                        tray_data['humidity'] = h_pct or h_index
                        tray_data['humidity_pct'] = h_pct
                        tray_data['temp'] = ams_temp
                        
                    trays.append(tray_data)

            # 2. Processar VT Tray (Carretel Externo/Lateral)
            if vt_data:
                is_active = (active_ams == 254 or active_ams == 255) # 255 as vezes significa externo em alguns modelos
                f_type = vt_data.get('tray_type', '')
                f_color = vt_data.get('tray_color', 'FFFFFF')
                if not f_color.startswith('#'): f_color = '#' + f_color
                f_remain = vt_data.get('remain', -1)
                idx = vt_data.get('tray_info_idx', '')
                f_brand = vt_data.get('tray_sub_brands', '')
                f_uuid = vt_data.get('tray_uuid', '')
                
                # Identificar nome amigável
                f_name = get_bambu_filament_name(idx)
                if f_name == "Unknown" and f_brand:
                    f_name = f"{f_brand} {f_type}".strip()
                elif f_name == "Unknown":
                    f_name = f_type or "Desconhecido"

                # Só adicionar se não estiver totalmente vazio ou se for o ativo
                if f_type or is_active:
                    trays.append({
                        'ams': 254, # ID reservado para Externo
                        'id': 0,
                        'type': f_type,
                        'brand': f_brand,
                        'name': f_name,
                        'uuid': f_uuid,
                        'color': f_color,
                        'remain': f_remain,
                        'humidity': 'N/A',
                        'active': is_active,
                        'empty': not f_type
                    })

            if trays:
                self.status['ams'] = trays
                # Encontrar nome do tray ativo
                active_t = next((t for t in trays if t['active']), None)
                if active_t:
                    self.status['active_tray_name'] = active_t['name']
                    self.status['active_tray_uuid'] = active_t.get('uuid', '')
                else:
                    self.status['active_tray_name'] = 'None'
                    self.status['active_tray_uuid'] = ''

            # Firmware Upgrade State
            upgrade = data.get('upgrade_state') or p.get('upgrade_state')
            if upgrade:
                self.status['firmware_update']['available'] = (upgrade.get('new_version_state') == 1)
                # Tentar pegar versão ota do P1/X1
                new_ver_list = upgrade.get('new_ver_list', [])
                for v in new_ver_list:
                    if v.get('name') == 'ota':
                        self.status['firmware_update']['current'] = v.get('cur_ver', self.status['firmware_update']['current'])
                        self.status['firmware_update']['latest'] = v.get('new_ver', '')
                
                # Caso do X1 que as vezes manda direto no objeto
                if 'ota_new_version_number' in upgrade:
                    latest = upgrade['ota_new_version_number']
                    if latest: self.status['firmware_update']['latest'] = latest

            # Dados do comando "info" (get_version)
            info = data.get('info', {})
            if info:
                msg = info.get('command')
                if msg == 'get_version':
                    # Detectar modelo da impressora via product_name
                    MODEL_MAP = {
                        'Bambu Lab H2D': 'H2D', 'Bambu Lab H2D Pro': 'H2DPRO',
                        'Bambu Lab H2C': 'H2C', 'Bambu Lab H2S': 'H2S',
                        'Bambu Lab P2S': 'P2S', 'Bambu Lab X2D': 'X2D',
                        'Bambu Lab X1C': 'X1C', 'Bambu Lab X1E': 'X1E',
                        'Bambu Lab P1S': 'P1S', 'Bambu Lab P1P': 'P1P',
                        'Bambu Lab A1': 'A1', 'Bambu Lab A1 mini': 'A1MINI',
                    }
                    for dev in info.get('module', []):
                        pname = dev.get('product_name', '')
                        if pname and pname in MODEL_MAP:
                            self.status['device_model'] = MODEL_MAP[pname]
                        if dev.get('name') == 'ota':
                            self.status['firmware_update']['current'] = dev.get('sw_ver', '')
                    
                    # Tentar pegar usage hours se reportado
                    if 'usage_hours' in info:
                        self.status['total_usage'] = info['usage_hours']

            # Track usage hours localmente se não vier da impressora
            if self.status['state'] in ['running', 'printing']:
                if self.start_time is None:
                    self.start_time = time.time()
                else:
                    # Incrementar uso (aproximado)
                    now = time.time()
                    self.status['total_usage'] += (now - self.start_time) / 3600.0
                    self.start_time = now
            else:
                self.start_time = None

    def _start_metadata_fetch(self, filename):
        if self.metadata_thread and self.metadata_thread.is_alive():
            return
        self.metadata_thread = threading.Thread(target=self._fetch_metadata_ftp, args=(filename,), daemon=True)
        self.metadata_thread.start()

    def _fetch_metadata_ftp(self, filename):
        # Retries are important for X1C as the file might not be ready immediately
        # Aumentado para 12 tentativas (aprox 60s) como no exemplo oficial
        for attempt in range(12):
            try:
                log_debug(f"[{self.ip}] FTP Metadata (Tentativa {attempt+1}): {filename}")
                context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                
                ftp = ImplicitFTP_TLS(context=context)
                ftp.connect(self.ip, 990, timeout=10)
                ftp.login("bblp", self.access_code)
                ftp.prot_p()
                
                # Lista de caminhos para tentar encontrar o 3mf
                # X1C e P1P as vezes usam nomes fixos ou pastas diferentes
                search_files = [filename]
                if not filename.endswith('.3mf'):
                    search_files.append(filename + ".3mf")
                    search_files.append(filename + ".gcode.3mf")
                
                # Nomes comuns em impressões via cloud
                search_files.extend(["ftp_model.3mf", "model.3mf", "_model_.3mf"])
                
                target_path = None
                for f_name in search_files:
                    for folder in ["/data/Metadata", "/cache", ""]:
                        p = f"{folder}/{f_name}" if folder else f"/{f_name}"
                        try:
                            # log_debug(f"[{self.ip}] Testando FTP: {p}")
                            ftp.size(p)
                            target_path = p
                            log_info(f"[{self.ip}] FTP: Encontrado arquivo de metadados: {p}")
                            break
                        except: continue
                    if target_path: break
                
                if not target_path:
                    log_info(f"[{self.ip}] FTP: Nenhum arquivo de metadados encontrado para '{filename}'. Tentando listar diretórios...")
                    try:
                        for folder in ["/", "/cache", "/data/Metadata"]:
                            files = []
                            ftp.retrlines(f"LIST {folder}", files.append)
                            log_info(f"[{self.ip}] Conteúdo de {folder}: {files[:5]}") # Mostrar apenas os 5 primeiros para não lotar o log
                    except: pass
                    
                if target_path:
                    log_info(f"[{self.ip}] FTP: Baixando {target_path}...")
                    bio = io.BytesIO()
                    ftp.retrbinary(f"RETR {target_path}", bio.write)
                    ftp.quit()
                    
                    bio.seek(0)
                    with zipfile.ZipFile(bio) as z:
                        # Ler slice_info.config para peso
                        try:
                            with z.open('Metadata/slice_info.config') as f:
                                tree = ET.parse(f)
                                plate = tree.find('plate')
                                if plate is not None:
                                    plate_idx = '1'
                                    for meta in plate:
                                        if meta.get('key') == 'weight':
                                            self.status['print_weight'] = float(meta.get('value'))
                                        elif meta.get('key') == 'prediction':
                                            # Estimativa de tempo em segundos para minutos
                                            self.status['total_duration'] = int(float(meta.get('value')) / 60)
                                        elif meta.get('key') == 'index':
                                            plate_idx = meta.get('value')
                                    
                                    # Tentar imagem do plate (várias nomenclaturas comuns)
                                    possible_images = [
                                        f'Metadata/plate_{plate_idx}.png',
                                        f'Metadata/plate_1.png',
                                        f'Metadata/plate_0.png',
                                        f'Metadata/thumbnail.png',
                                        f'Metadata/top.png'
                                    ]
                                    for img_path in possible_images:
                                        try:
                                            with z.open(img_path) as img_f:
                                                self.status['cover_image'] = base64.b64encode(img_f.read()).decode('utf-8')
                                                log_info(f"[{self.ip}] Thumbnail encontrada e carregada: {img_path}")
                                                break
                                        except: continue
                        except Exception as e:
                            log_info(f"[{self.ip}] Erro ao processar Zip: {e}")
                    return # Sucesso
                else:
                    ftp.quit()
            except Exception as e:
                log_debug(f"[{self.ip}] Erro FTP (Tentativa {attempt+1}): {e}")
            
            # Aguardar antes de tentar novamente
            time.sleep(5)

    def list_bambu_files(self, category='files'):
        """
        Lista arquivos do cartão SD via FTP.
        category: 'files' (mapeia para fatiamentos) ou 'timelapse' (mapeia para vídeos)
        """
        # Pastas conhecidas dependendo da versão do firmware e modelo (A1/P1/X1)
        if category == 'files':
            paths_to_check = ["/model", "/", "/cache", "/data/Metadata"]
        else:
            paths_to_check = ["/timelapse", "/timelapse/video", "/record", "/recording"]
            
        log_info(f"[{self.ip}] FTP: Listando arquivos da categoria {category}")
        
        all_files = []
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            ftp = ImplicitFTP_TLS(context=context)
            ftp.connect(self.ip, 990, timeout=10)
            ftp.login("bblp", self.access_code)
            ftp.prot_p()
            
            for path in paths_to_check:
                try:
                    ftp.cwd(path)
                    items = []
                    ftp.retrlines("LIST", items.append)
                    
                    for item in items:
                        parts = item.split()
                        if len(parts) >= 9:
                            is_dir = item.startswith('d')
                            name = " ".join(parts[8:])
                            # Ignorar arquivos de sistema ou ocultos
                            if name in ['.', '..'] or name.startswith('._'): continue
                            
                            # Filtro básico
                            lower_name = name.lower()
                            if category == 'files' and not (lower_name.endswith('.3mf') or lower_name.endswith('.gcode') or is_dir):
                                continue
                            if category == 'timelapse' and not (lower_name.endswith('.mp4') or lower_name.endswith('.avi') or is_dir):
                                continue
                                
                            size = int(parts[4])
                            p_path = f"{path.rstrip('/')}/{name}"
                            
                            # Evitar duplicatas que podem ocorrer por symlinks ou caminhos relativos
                            if not any(f['path'] == p_path for f in all_files):
                                all_files.append({
                                    'name': name,
                                    'is_dir': is_dir,
                                    'size': size,
                                    'path': p_path
                                })
                except Exception as e:
                    pass # Pasta não existe ou sem permissão, normal
            
            ftp.quit()
        except Exception as e:
            log_error(f"[{self.ip}] Erro ao listar arquivos via FTP: {e}")
            
        # Ordenar por nome
        all_files.sort(key=lambda x: x['name'], reverse=True if category == 'timelapse' else False)
        return all_files

    def download_bambu_file(self, remote_path):
        """Baixa um arquivo do FTP e retorna os bytes."""
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            ftp = ImplicitFTP_TLS(context=context)
            ftp.connect(self.ip, 990, timeout=15)
            ftp.login("bblp", self.access_code)
            ftp.prot_p()
            
            bio = io.BytesIO()
            ftp.retrbinary(f"RETR {remote_path}", bio.write)
            ftp.quit()
            bio.seek(0)
            return bio.read()
        except Exception as e:
            log_error(f"[{self.ip}] Erro ao baixar arquivo FTP ({remote_path}): {e}")
            return None

    def delete_bambu_file(self, remote_path):
        """Remove um arquivo do cartão SD via FTP."""
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            ftp = ImplicitFTP_TLS(context=context)
            ftp.connect(self.ip, 990, timeout=10)
            ftp.login("bblp", self.access_code)
            ftp.prot_p()
            
            log_info(f"[{self.ip}] FTP: Removendo {remote_path}")
            ftp.delete(remote_path)
            ftp.quit()
            return True
        except Exception as e:
            log_error(f"[{self.ip}] Erro ao remover arquivo FTP ({remote_path}): {e}")
            return False

    def update(self):
        # Incrementar horas de uso se estiver imprimindo
        now = time.time()
        if self.status.get('state', '').lower() in ['running', 'printing']:
            delta = now - self.last_usage_time
            self.status['total_usage'] = self.status.get('total_usage', 0) + (max(0, delta) / 3600.0)
        self.last_usage_time = now

        if not self.connected_flag or (time.time() - self.last_update > 30):
            self.request_push()
            if time.time() - self.last_update > 60:
                 self.status['state'] = 'offline'

    def send_command(self, command, **kwargs):
        if not self.connected_flag: return
        topic = f"device/{self.serial}/request"
        
        msg = {}
        if command == 'pause':
            msg = {"print": {"command": "pause", "sequence_id": "0"}}
        elif command == 'resume':
            msg = {"print": {"command": "resume", "sequence_id": "0"}}
        elif command == 'stop':
            msg = {"print": {"command": "stop", "sequence_id": "0"}}
        elif command == 'led':
            val = int(kwargs.get('val', 0))
            msg = {"system": {"sequence_id": "0", "command": "ledctrl", "led_node": "chamber_light", "led_mode": "on" if val > 0 else "off"}}
        elif command == 'speed':
            val = int(kwargs.get('val', 2))
            msg = {"print": {"sequence_id": "0", "command": "speed_level", "param": str(val)}}
        
        # Movement and extrusion controls REMOVED as per user request
        # elif command == 'home': ...
        # elif command == 'move': ...
        # elif command == 'extrude': ...
        # elif command == 'motors_off': ...
        
        if msg:
            self.client.publish(topic, json.dumps(msg))


def create_printer_from_config(config):
    p_type = config.get('type')
    if p_type == 'moonraker':
        return MoonrakerPrinter(config)
    elif p_type == 'elegoo':
        return ElegooPrinter(config)
    elif p_type == 'bambu':
        p = BambuPrinter(config)
        p.connect()
        return p
    return None
