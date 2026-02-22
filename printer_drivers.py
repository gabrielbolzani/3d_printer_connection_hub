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
from datetime import datetime, timedelta
from logger_config import log_info, log_error, log_debug, log_warn

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
            'total_usage': config.get('total_usage', 0.0)
        }
        self.last_update = 0
        self.last_usage_time = time.time()

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
            'fan_part': 0,
            'fan_aux': 0,
            'fan_chamber': 0,
            'ams': [],
            'hms': [],
            'wifi_signal': 0
        })
        self.last_frame = None

    def send_command(self, command, **kwargs):
        pass

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
        s['enabled'] = self.config.get('enabled', True)
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
            return
        try:
            url = f"http://{self.ip}/server/files/metadata?filename={filename}"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                data = resp.json().get('result', {})
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
                        finish_dt = datetime.now() + timedelta(minutes=rem_time)
                        self.status['finish_time'] = finish_dt.strftime("%H:%M")
                    elif prog >= 1:
                        self.status['remaining_time'] = 0
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
        print(f"[{self.ip}] Iniciando thread da câmera (Match Exemplo)...")
        
        username = 'bblp'
        port = 6000
        
        # Payload de autenticação - Montagem byte a byte idêntica ao exemplo funcional
        auth_data = bytearray()
        auth_data += struct.pack("<I", 0x40)   # Payload size (64 bytes)
        auth_data += struct.pack("<I", 0x3000) # Type
        auth_data += struct.pack("<I", 0)      # Seq
        auth_data += struct.pack("<I", 0)      # Reserved
        
        # Username (32 bytes)
        for i in range(len(username)):
            auth_data += struct.pack("<c", username[i].encode('ascii'))
        for i in range(32 - len(username)):
            auth_data += struct.pack("<x")
            
        # Access Code (32 bytes) - Respeita o case fornecido pelo usuário
        for i in range(len(self.access_code)):
            auth_data += struct.pack("<c", self.access_code[i].encode('ascii'))
        for i in range(32 - len(self.access_code)):
            auth_data += struct.pack("<x")

        # Contexto SSL - Refinado para X1C
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers('DEFAULT@SECLEVEL=1:AES128-SHA')
        # Desabilita protocolos inseguros mas mantém TLS 1.2
        ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1

        while not self._stop_event.is_set():
            try:
                # Usar socket puro para ter controle total do timeout antes do wrap
                sock = socket.create_connection((self.ip, port), timeout=3)
                sock.settimeout(3)
                # server_hostname=None to avoid SNI issues with IP addresses on some firmware
                try:
                    sslSock = ctx.wrap_socket(sock, server_hostname=None)
                except:
                    sock.close()
                    raise
                
                with sslSock:
                    log_debug(f"[{self.ip}] Câmera: Conexão SSL estabelecida (Match Exemplo).")
                    
                    # Atraso crucial para a X1C processar o handshake antes do auth
                    time.sleep(0.5)
                    sslSock.sendall(auth_data)
                    
                    buffer = bytearray()
                    sslSock.setblocking(False)
                    
                    while not self._stop_event.is_set():
                        try:
                            # Proteção contra soquetes fechados prematuramente
                            try:
                                ready = select.select([sslSock], [], [], 0.5)
                            except (OSError, ValueError):
                                break
                                
                            if not ready[0]: continue
                            
                            dr = sslSock.recv(16384)
                            if not dr: break
                            buffer += dr
                            
                            while len(buffer) >= 16:
                                payload_size = int.from_bytes(buffer[0:4], byteorder='little')
                                if payload_size > 1000000 or payload_size < 100:
                                    buffer = buffer[1:]
                                    continue
                                    
                                if len(buffer) < 16 + payload_size:
                                    break
                                
                                img_data = buffer[16:16+payload_size]
                                if img_data.startswith(b'\xff\xd8'):
                                    self.callback(bytes(img_data))
                                
                                buffer = buffer[16+payload_size:]
                                
                        except ssl.SSLWantReadError:
                            continue
                        except Exception as e:
                            log_debug(f"[{self.ip}] Câmera Loop: {e}")
                            break
            except Exception as e:
                if not self._stop_event.is_set():
                    # print(f"[{self.ip}] Câmera Erro: {e}")
                    pass
                if self._stop_event.wait(5): break
            except Exception as e:
                log_debug(f"[{self.ip}] Câmera: Erro de conexão/Auth: {e}")
                if self._stop_event.wait(5): break

    def stop(self):
        self._stop_event.set()
        # Não damos join aqui para não travar o loop principal, 
        # mas a thread é daemon então ok.

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
            'fan_part': 0,
            'fan_aux': 0,
            'fan_chamber': 0,
            'ams': [],
            'hms': [],
            'speed_level': 2, # Normal
            'wifi_signal': 0,
            'task_name': '',
            'print_weight': 0,
            'active_tray_name': 'None',
            'active_tray_uuid': '',
            'firmware_update': {'current': '', 'latest': '', 'available': False},
            'print_error': {'code': 0, 'message': ''}
        })
        # total_usage já está no BasePrinter.status
        self.start_time = None

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
            
            # Se 'print' não existe, data pode ser o próprio dicionário de status em alguns casos
            # Mas geralmente a Bambu manda {"print": {...}} ou {"ams": {...}}
            
            if p:
                if 'gcode_state' in p:
                    self.status['state'] = p['gcode_state'].lower()
                if 'mc_percent' in p:
                    self.status['progress'] = p['mc_percent']
                if 'mc_remaining_time' in p:
                    self.status['remaining_time'] = p['mc_remaining_time']
                    dt = datetime.now() + timedelta(minutes=p['mc_remaining_time'])
                    self.status['finish_time'] = dt.strftime("%H:%M")
                if 'nozzle_temper' in p:
                    self.status['temp_nozzle'] = p['nozzle_temper']
                if 'nozzle_target_temper' in p:
                    self.status['target_nozzle'] = p['nozzle_target_temper']
                if 'bed_temper' in p:
                    self.status['temp_bed'] = p['bed_temper']
                if 'bed_target_temper' in p:
                    self.status['target_bed'] = p['bed_target_temper']
                if 'chamber_temper' in p:
                    self.status['chamber_temp'] = p['chamber_temper']
                if 'subtask_name' in p:
                    new_file = p['subtask_name']
                    if new_file != self.current_filename and new_file:
                        self.current_filename = new_file
                        self.status['filename'] = new_file
                        # Simplificar nome da task
                        self.status['task_name'] = new_file.replace('.gcode', '').replace('.3mf', '')
                        # Resetar metadata p/ nova task
                        self.status['cover_image'] = None
                        self.status['print_weight'] = 0
                        # Tentar buscar metadata via FTP
                        self._start_metadata_fetch(new_file)
                if 'cooling_fan_speed' in p:
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
                    self.status['hms'] = p['hms']
                
                # Print Error e HMS handling
                if 'print_error' in p:
                    err_code = p['print_error']
                    self.status['print_error'] = {
                        'code': err_code,
                        'message': f"Erro {err_code:X}" if err_code != 0 else ""
                    }
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
                humidity = unit.get('humidity', '??')
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

                    trays.append({
                        'ams': unit_id,
                        'id': tray_id,
                        'type': f_type,
                        'brand': f_brand,
                        'name': f_name,
                        'color': f_color,
                        'remain': f_remain,
                        'uuid': f_uuid,
                        'humidity': humidity,
                        'active': is_active,
                        'empty': is_empty
                    })

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

            # Dados do comando "info" (get_version)
            info = data.get('info', {})
            if info:
                msg = info.get('command')
                if msg == 'get_version':
                    # Extrair versões
                    for dev in info.get('module', []):
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
                    for folder in ["/cache", ""]:
                        p = f"{folder}/{f_name}" if folder else f"/{f_name}"
                        try:
                            # log_debug(f"[{self.ip}] Testando FTP: {p}")
                            ftp.size(p)
                            target_path = p
                            break
                        except: continue
                    if target_path: break
                    
                if target_path:
                    log_debug(f"[{self.ip}] FTP: Baixando {target_path}...")
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
                                        elif meta.get('key') == 'index':
                                            plate_idx = meta.get('value')
                                    
                                    # Tentar imagem do plate
                                    try:
                                        with z.open(f'Metadata/plate_{plate_idx}.png') as img_f:
                                            self.status['cover_image'] = base64.b64encode(img_f.read()).decode('utf-8')
                                    except:
                                        # Fallback para plate_1 se o index falhar
                                        try:
                                            with z.open(f'Metadata/plate_1.png') as img_f:
                                                 self.status['cover_image'] = base64.b64encode(img_f.read()).decode('utf-8')
                                        except: pass
                        except Exception as e:
                            log_debug(f"[{self.ip}] Erro ao processar Zip: {e}")
                    return # Sucesso
                else:
                    ftp.quit()
            except Exception as e:
                log_debug(f"[{self.ip}] Erro FTP (Tentativa {attempt+1}): {e}")
            
            # Aguardar antes de tentar novamente
            time.sleep(5)

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
