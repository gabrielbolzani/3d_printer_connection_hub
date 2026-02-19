import json
import socket
import threading
import time
import queue
import ssl
import requests
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta

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

    def send_command(self, command, **kwargs):
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
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                data = response.json()
                res = data.get('result', {}).get('status', {})
                
                # Update status
                if 'print_stats' in res:
                    self.status['state'] = res['print_stats'].get('state', 'unknown')
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
        except Exception as e:
            # print(f"Moonraker update failed for {self.ip}: {e}")
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
                    json={'script': f'M106 S{pwm}'}, timeout=3)
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
                fval = val / 100.0
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'SET_PIN PIN=fan1 VALUE={fval:.2f}'}, timeout=3)
            elif command == 'fan_chamber':
                val = int(kwargs.get('val', 0))
                fval = val / 100.0
                requests.post(f"http://{self.ip}/printer/gcode/script",
                    json={'script': f'SET_PIN PIN=fan2 VALUE={fval:.2f}'}, timeout=3)
            elif command == 'reboot':
                requests.post(f"http://{self.ip}/machine/reboot", timeout=3)
        except Exception as e:
            print(f"Moonraker command error: {e}")

# Elegoo (Saturn 3 Ultra) Implementation - UDP
class ElegooPrinter(BasePrinter):
    def __init__(self, config):
        super().__init__(config)
        self.port = config.get('port', 3000)
        # Resin printers don't have nozzle/bed temperatures
        self.status.pop('temp_nozzle', None)
        self.status.pop('temp_bed', None)

    def _send_command(self, message):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2)
            sock.sendto(message.encode(), (self.ip, self.port))
            data, _ = sock.recvfrom(4096)
            return json.loads(data.decode())
        except Exception as e:
            # print(f"Elegoo error: {e}")
            return None
        finally:
            try:
                sock.close()
            except:
                pass

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

# Bambu Lab Implementation - MQTT
class BambuPrinter(BasePrinter):
    def __init__(self, config):
        super().__init__(config)
        self.serial = config.get('serial')
        self.access_code = config.get('access_code')
        self.client = None
        self.connected_flag = False
        self.lock = threading.Lock()

    def connect(self):
        if self.client:
            return

        self.client = mqtt.Client(client_id=f"aditiva-{int(time.time())}")
        self.client.username_pw_set("bblp", self.access_code)
        
        # SSL Context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self.client.tls_set_context(context)
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        try:
            self.client.connect(self.ip, 8883, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"Bambu connection failed: {e}")
            self.status['state'] = 'offline'

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected_flag = True
            topic = f"device/{self.serial}/report"
            client.subscribe(topic)
            # Subscribe succeeded, request initial push
            self.request_push()

    def request_push(self):
        if not self.connected_flag: return
        msg = {
            "pushing": {
                "sequence_id": "0",
                "command": "pushall"
            }
        }
        topic = f"device/{self.serial}/request"
        self.client.publish(topic, json.dumps(msg))

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self.parse_bambu_json(payload)
            self.last_update = time.time()
        except Exception as e:
            print(f"Error parsing Bambu msg: {e}")

    def parse_bambu_json(self, data):
        with self.lock:
            # Basic parsing logic based on standard Bambu report
            print_data = data.get('print', {})
            if not print_data: return

            if 'gcode_state' in print_data:
                self.status['state'] = print_data['gcode_state']
            
            if 'mc_percent' in print_data:
                self.status['progress'] = print_data['mc_percent']
            
            if 'mc_remaining_time' in print_data:
                self.status['remaining_time'] = print_data['mc_remaining_time']

            if 'nozzle_temper' in print_data:
                self.status['temp_nozzle'] = print_data['nozzle_temper']
            
            if 'bed_temper' in print_data:
                self.status['temp_bed'] = print_data['bed_temper']
            
            if 'subtask_name' in print_data:
                self.status['filename'] = print_data['subtask_name']

    def update(self):
        # Bambu updates via MQTT callback, but we can check connection here
        if not self.connected_flag or (time.time() - self.last_update > 30):
            # If no update for 30s, try reconnecting or requesting push
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
            msg = {
                "system": {
                    "sequence_id": "0",
                    "command": "ledctrl",
                    "led_node": "chamber_light",
                    "led_mode": "on" if val > 0 else "off",
                    "led_on_time": 500,
                    "led_off_time": 500,
                    "loop_times": 0,
                    "interval_time": 0
                }
            }
        
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
