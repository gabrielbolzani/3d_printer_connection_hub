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
from datetime import datetime, timedelta
from logger_config import log_info, log_error, log_debug, log_warn

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
            'finish_time': '--'
        }
        self.last_update = 0

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
        s['camera_refresh'] = self.config.get('camera_refresh', False)
        s['refresh_interval'] = self.config.get('refresh_interval', 5000)
        s['enabled'] = self.config.get('enabled', True)
        s['last_update'] = self.last_update
        return s

# Moonraker (Klipper) Implementation
class MoonrakerPrinter(BasePrinter):
    def update(self):
        try:
            url = f"http://{self.ip}/printer/objects/query?print_stats&extruder&heater_bed&display_status&fan&toolhead&temperature_sensor%20mcu_temp&temperature_sensor%20chamber_temp&system_stats"
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                res = data.get('result', {}).get('status', {})
                
                # Update status
                if 'print_stats' in res:
                    state = res['print_stats'].get('state', 'unknown')
                    # Map 'standby' to 'idle' for UI consistency
                    self.status['state'] = 'idle' if state == 'standby' else state
                    self.status['filename'] = res['print_stats'].get('filename', '')
                    self.status['print_duration'] = res['print_stats'].get('print_duration', 0)
                
                if 'extruder' in res:
                    self.status['temp_nozzle'] = res['extruder'].get('temperature', 0)
                    self.status['target_nozzle'] = res['extruder'].get('target', 0)
                
                if 'heater_bed' in res:
                    self.status['temp_bed'] = res['heater_bed'].get('temperature', 0)
                    self.status['target_bed'] = res['heater_bed'].get('target', 0)
                
                if 'display_status' in res:
                    self.status['progress'] = res['display_status'].get('progress', 0) * 100
                
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
                pwm = int(val / 100 * 255)
                fval = val / 100.0
                # Try both M106 and SET_PIN for compatibility with different K1/Klipper setups
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'M106 P0 S{pwm}'}, timeout=3)
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'SET_PIN PIN=fan0 VALUE={fval:.2f}'}, timeout=3)
            elif command == 'led':
                val = int(kwargs.get('val', 0))
                pwm = int(val / 100 * 255)
                fval = val / 100.0
                # M355 is standard for some, others use SET_PIN
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'M355 S{1 if val > 0 else 0} P{pwm}'}, timeout=3)
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'SET_PIN PIN=LED VALUE={fval:.2f}'}, timeout=3)
                # K1 Max specific often uses caselight pin
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'SET_PIN PIN=caselight VALUE={fval:.2f}'}, timeout=3)

            elif command == 'fan_aux':
                val = int(kwargs.get('val', 0))
                pwm = int(val / 100 * 255)
                fval = val / 100.0
                # K1 Max Aux Fan is usually M106 P2
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'M106 P2 S{pwm}'}, timeout=3)
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'SET_PIN PIN=fan1 VALUE={fval:.2f}'}, timeout=3)
            elif command == 'fan_chamber':
                val = int(kwargs.get('val', 0))
                pwm = int(val / 100 * 255)
                fval = val / 100.0
                # K1 Max Chamber Fan is usually M106 P3
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'M106 P3 S{pwm}'}, timeout=3)
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'SET_PIN PIN=fan2 VALUE={fval:.2f}'}, timeout=3)
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
        auth_data += struct.pack("<I", 0x40)   # Magic @
        auth_data += struct.pack("<I", 0x3000) # Type
        auth_data += struct.pack("<I", 0)      # Seq
        auth_data += struct.pack("<I", 64)     # Length (32 user + 32 pass)
        
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
                sock = socket.create_connection((self.ip, port), timeout=5)
                with ctx.wrap_socket(sock, server_hostname=self.ip) as sslSock:
                    log_debug(f"[{self.ip}] Câmera: Conexão SSL estabelecida.")
                    
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
            'wifi_signal': 0
        })

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
        log_info(f"[{self.ip}] Parando serviços Bambu...")
        if self.client:
            try:
                self.client.disconnect()
                self.client.loop_stop()
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
        msg = {"pushing": {"sequence_id": "0", "command": "pushall"}}
        self.client.publish(f"device/{self.serial}/request", json.dumps(msg))

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
                    self.status['filename'] = p['subtask_name']
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
                    
                    # Um slot é considerado vazio se não tiver tipo nem idx
                    is_empty = not f_type and not idx
                    
                    trays.append({
                        'ams': unit_id,
                        'id': tray_id,
                        'type': f_type or 'Vazio',
                        'brand': f_brand,
                        'color': f_color,
                        'remain': f_remain,
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
                
                # Só adicionar se não estiver totalmente vazio ou se for o ativo
                if f_type or is_active:
                    trays.append({
                        'ams': 254, # ID reservado para Externo
                        'id': 0,
                        'type': f_type or 'Externo',
                        'brand': vt_data.get('tray_sub_brands', 'Manual'),
                        'color': f_color,
                        'remain': f_remain,
                        'humidity': 'N/A',
                        'active': is_active,
                        'empty': not f_type
                    })

            if trays:
                self.status['ams'] = trays

    def update(self):
        if not self.connected_flag or (time.time() - self.last_update > 30):
            self.request_push()
            if time.time() - self.last_update > 60:
                 self.status['state'] = 'offline'

    def send_command(self, command, **kwargs):
        if not self.connected_flag: return
        topic = f"device/{self.serial}/request"
        
        msg = {}
        if command == 'pause':
            msg = {"printing": {"command": "pause", "sequence_id": "0"}}
        elif command == 'resume':
            msg = {"printing": {"command": "resume", "sequence_id": "0"}}
        elif command == 'stop':
            msg = {"printing": {"command": "stop", "sequence_id": "0"}}
        elif command == 'led':
            val = int(kwargs.get('val', 0))
            msg = {"system": {"sequence_id": "0", "command": "ledctrl", "led_node": "chamber_light", "led_mode": "on" if val > 0 else "off"}}
        elif command == 'speed':
            val = int(kwargs.get('val', 2))
            msg = {"print": {"sequence_id": "0", "command": "speed_level", "param": str(val)}}
        elif command == 'home':
            msg = {"print": {"sequence_id": "0", "command": "gcode_line", "param": "G28\n"}}
        elif command == 'move':
            axis = kwargs.get('axis', 'X')
            dist = kwargs.get('dist', 10)
            msg = {"print": {"sequence_id": "0", "command": "gcode_line", "param": f"G91\nG1 {axis}{dist} F3000\nG90\n"}}
        elif command == 'extrude':
            dist = kwargs.get('dist', 5)
            msg = {"print": {"sequence_id": "0", "command": "gcode_line", "param": f"M83\nG1 E{dist} F300\n"}}
        elif command == 'motors_off':
            msg = {"print": {"sequence_id": "0", "command": "gcode_line", "param": "M84\n"}}
        
        if msg:
            self.client.publish(topic, json.dumps(msg))

    def stop(self):
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except: pass
        if self.cam_thread:
            self.cam_thread.stop()

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
