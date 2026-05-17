from flask import Flask, render_template, request, jsonify, abort, send_file
import io
import threading
import time
import json
import os
import psutil
import signal
import sys
import requests
import base64
from datetime import datetime, timedelta
from printer_drivers import create_printer_from_config
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

@app.context_processor
def inject_version():
    try:
        v_path = get_resource_path("VERSION")
        if not os.path.exists(v_path):
            # Fallback para raiz se não estiver no bundle ou cwd
            v_path = "VERSION"
        with open(v_path, "r") as f:
            v = f.read().strip()
    except:
        v = "v1.6.0"
    return dict(app_version=v)

CONFIG_FILE = 'config.json'
ENERGY_CONFIG_FILE = 'energy_config.json'
PRINTERS = []
PRINTERS_LOCK = threading.Lock()
STATUS_CACHE = {}
APP_START_TIME = time.time()
APP_START_TIME = time.time()
from logger_config import log_info as py_log_info, log_error as py_log_error, log_warn as py_log_warn, log_debug as py_log_debug

LOG_BUFFER = []
MAX_LOG_SIZE = 500
LOG_ID_COUNTER = 0

def add_to_console(level, message):
    global LOG_ID_COUNTER
    LOG_ID_COUNTER += 1
    log_entry = {
        'id': LOG_ID_COUNTER,
        'time': time.strftime('%H:%M:%S'),
        'level': level,
        'message': str(message)
    }
    LOG_BUFFER.append(log_entry)
    if len(LOG_BUFFER) > MAX_LOG_SIZE:
        LOG_BUFFER.pop(0)

# Redefine log helpers to also send to console
def log_info(msg): 
    py_log_info(msg)
    add_to_console("INFO", msg)

def log_error(msg): 
    py_log_error(msg)
    add_to_console("ERROR", msg)

def log_warn(msg): 
    py_log_warn(msg)
    add_to_console("WARN", msg)

def log_debug(msg): 
    py_log_debug(msg)
    add_to_console("DEBUG", msg)

def log_cloud(msg):
    py_log_info(f"[Cloud] {msg}")
    add_to_console("CLOUD", msg)

AUTH_FILE = 'auth_token.json'
SYNC_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'sync_config.json')

# Global state for rate calculations
LAST_PROC_IO = None
LAST_PROC_TIME = None
APP_START_TIME = time.time()
executor = ThreadPoolExecutor(max_workers=20)
KEEP_RUNNING = True
PREVIOUS_PRINTER_STATES = {} # Para detecção de conclusão de impressão
CLOUD_METADATA = {'user_id': None, 'machines': {}, 'last_refresh': 0}

# ── Configuração de Sincronização ────────────────────────────────────────────
# sync_on_device_poll: True  → transmite cada dispositivo de energia assim que
#                             termina a leitura local (respeita polling_interval)
# sync_on_device_poll: False → transmite todos no intervalo fixo (sync_interval_s)
SYNC_CONFIG_LOCK = threading.Lock()
# Fila de dispositivos de energia prontos para sync imediato
import queue as _queue_mod
ENERGY_SYNC_QUEUE = _queue_mod.Queue()

def load_sync_config():
    with SYNC_CONFIG_LOCK:
        if not os.path.exists(SYNC_CONFIG_FILE):
            return {'sync_interval_s': 5, 'sync_on_device_poll': False}
        try:
            with open(SYNC_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {
                    'sync_interval_s': int(data.get('sync_interval_s', 5)),
                    'sync_on_device_poll': bool(data.get('sync_on_device_poll', False))
                }
        except:
            return {'sync_interval_s': 5, 'sync_on_device_poll': False}

def save_sync_config(cfg):
    with SYNC_CONFIG_LOCK:
        try:
            with open(SYNC_CONFIG_FILE + '.tmp', 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
            os.replace(SYNC_CONFIG_FILE + '.tmp', SYNC_CONFIG_FILE)
        except Exception as e:
            log_error(f'Erro ao salvar sync_config: {e}')

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return []
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, IOError):
        # In case of read error (e.g. file being written), return None to indicate failure
        return None

def save_config(printers_config):
    # Use temporary file for atomic write
    temp_file = CONFIG_FILE + '.tmp'
    try:
        with open(temp_file, 'w') as f:
            json.dump(printers_config, f, indent=4)
        os.replace(temp_file, CONFIG_FILE)
    except Exception as e:
        print(f"Error saving config: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)

ENERGY_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'energy_config.json')
ENERGY_LOGS_FILE = os.path.join(os.path.dirname(__file__), 'energy_logs.json')
ENERGY_TELEMETRY = {} # Cache para telemetria em tempo real
SERIAL_LOCKS = {} # Locks por porta COM

def load_energy_logs():
    if not os.path.exists(ENERGY_LOGS_FILE):
        return {}
    try:
        with open(ENERGY_LOGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_energy_logs():
    try:
        with open(ENERGY_LOGS_FILE + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(ENERGY_LOGS, f, indent=4, ensure_ascii=False)
        os.replace(ENERGY_LOGS_FILE + '.tmp', ENERGY_LOGS_FILE)
    except Exception as e:
        print(f"Erro ao salvar energy_logs: {e}")

ENERGY_LOGS = load_energy_logs()

def log_energy_event(device_id, message):
    if str(device_id) not in ENERGY_LOGS:
        ENERGY_LOGS[str(device_id)] = []
    event = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "date": datetime.now().strftime("%d/%m/%Y"),
        "msg": message
    }
    ENERGY_LOGS[str(device_id)].insert(0, event)
    if len(ENERGY_LOGS[str(device_id)]) > 50:
        ENERGY_LOGS[str(device_id)].pop()
    save_energy_logs()
    # Envia também para o console principal da aplicação
    log_info(f"[Nobreak] {message}")

def get_serial_lock(port):
    if port not in SERIAL_LOCKS:
        SERIAL_LOCKS[port] = threading.Lock()
    return SERIAL_LOCKS[port]

ENERGY_CONFIG_LOCK = threading.Lock()

def load_energy_config():
    with ENERGY_CONFIG_LOCK:
        if not os.path.exists(ENERGY_CONFIG_FILE):
            return []
        try:
            with open(ENERGY_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except:
            return []

def save_energy_config(config):
    with ENERGY_CONFIG_LOCK:
        try:
            with open(ENERGY_CONFIG_FILE + '.tmp', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            os.replace(ENERGY_CONFIG_FILE + '.tmp', ENERGY_CONFIG_FILE)
        except Exception as e:
            log_error(f"Erro ao salvar energy_config: {e}")

def read_nut_vars(host, port, ups_name, user='', password=''):
    """Lê variáveis do servidor NUT via TCP e retorna um dicionário com os dados."""
    import socket
    NUT_VARS = [
        'input.voltage', 'output.voltage', 'output.frequency',
        'ups.load', 'battery.charge', 'battery.voltage',
        'ups.temperature', 'ups.status', 'ups.realpower', 'output.current'
    ]
    result = {}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, int(port)))
        
        def send_cmd(cmd):
            sock.send((cmd + '\n').encode())
            return sock.recv(512).decode().strip()
        
        if user:
            send_cmd(f'USERNAME {user}')
            send_cmd(f'PASSWORD {password}')
        
        for var in NUT_VARS:
            try:
                resp = send_cmd(f'GET VAR {ups_name} {var}')
                # Formato: VAR ups input.voltage "127.4"
                if resp.startswith('VAR'):
                    value = resp.split('"')[1]
                    result[var] = value
            except: pass
        
        send_cmd('LOGOUT')
        sock.close()
    except Exception as e:
        raise Exception(f"Falha NUT {host}:{port} - {e}")
    return result

def energy_polling_loop():
    """Monitoramento em background para dispositivos de energia"""
    import serial
    import binascii
    device_last_poll = {}
    
    while KEEP_RUNNING:
        try:
            config = load_energy_config()
            if not config:
                time.sleep(5)
                continue
                
            now = time.time()
            
            for dev in config:
                integration = dev.get('integration')
                interval = float(dev.get('polling_interval', 3.0))
                last_dev_poll = device_last_poll.get(dev['id'])
                
                if last_dev_poll and (now - last_dev_poll) < interval:
                    continue
                
                # Registra timestamp antes de processar (usado pelo NUT e Tasmota também)
                _sync_on_poll = load_sync_config().get('sync_on_device_poll')
                
                dt = now - last_dev_poll if last_dev_poll else 0.0
                device_last_poll[dev['id']] = now
                
                # ── NUT ──────────────────────────────────────────────────
                if integration == 'nut':
                    host = dev.get('nut_host', '')
                    nut_port = dev.get('nut_port', 3493)
                    ups_name = dev.get('nut_ups_name', 'ups')
                    user = dev.get('nut_user', '')
                    password = dev.get('nut_password', '')
                    if not host: continue
                    
                    try:
                        vars = read_nut_vars(host, nut_port, ups_name, user, password)
                        
                        input_vac  = float(vars.get('input.voltage', 0))
                        output_vac = float(vars.get('output.voltage', 0))
                        output_hz  = float(vars.get('output.frequency', 0))
                        load_pct   = float(vars.get('ups.load', 0))
                        batt_level = float(vars.get('battery.charge', 0))
                        batt_v_raw = vars.get('battery.voltage')
                        temp_c     = float(vars.get('ups.temperature', 0))
                        status_str = vars.get('ups.status', '')
                        
                        # Interpreta status NUT: OL=rede, OB=bateria, LB=baixa
                        em_uso = 'OB' in status_str
                        batt_baixa = 'LB' in status_str
                        
                        # Tensão da bateria (somente se for válida)
                        v_batt = None
                        prev_tel = ENERGY_TELEMETRY.get(dev['id'], {}).get('telemetry', {})
                        if batt_v_raw:
                            try:
                                val = float(batt_v_raw)
                                if 10.0 < val < 70.0:
                                    v_batt = val
                            except: pass
                        last_v = prev_tel.get('lastBatteryVoltage')
                        last_ts = prev_tel.get('lastBatteryTimestamp')
                        if v_batt is not None:
                            last_v = v_batt; last_ts = time.time()
                        
                        # Tenta usar potência real do NUT, senão calcula
                        watts = 0.0
                        if 'ups.realpower' in vars:
                            try:
                                watts = float(vars['ups.realpower'])
                            except: pass
                        
                        if watts == 0.0 and load_pct > 0:
                            nominal_va = dev.get('nominal_va', 1800.0)
                            fp = dev.get('power_factor', 0.7)
                            watts = (load_pct / 100.0) * (nominal_va * fp)
                            
                        # Tenta usar corrente do NUT, senão calcula
                        current_a = 0.0
                        if 'output.current' in vars:
                            try:
                                current_a = float(vars['output.current'])
                            except: pass
                            
                        if current_a == 0.0 and output_vac > 50:
                            current_a = watts / output_vac
                        
                        prev = ENERGY_TELEMETRY.get(dev['id'], {}).get('telemetry', {})
                        peak_watts = max(round(watts, 1), prev.get('peakWatts', 0))
                        peak_current = max(round(current_a, 2), prev.get('peakCurrent', 0))
                        min_vac = prev.get('minInputVac', input_vac)
                        max_vac = prev.get('maxInputVac', input_vac)
                        if input_vac > 50:
                            if min_vac < 50 or input_vac < min_vac: min_vac = input_vac
                            if input_vac > max_vac: max_vac = input_vac
                        
                        if dt > 0 and output_vac > 0:
                            kwh_gain = (watts * (dt / 3600.0)) / 1000.0
                            current_config = load_energy_config()
                            for c_dev in current_config:
                                if str(c_dev.get('id')) == str(dev['id']):
                                    c_dev['accumulated_kwh'] = c_dev.get('accumulated_kwh', 0.0) + kwh_gain
                                    dev['accumulated_kwh'] = c_dev['accumulated_kwh']
                                    break
                            save_energy_config(current_config)
                        
                        ENERGY_TELEMETRY[dev['id']] = {
                            "success": True,
                            "telemetry": {
                                "inputVac": input_vac, "outputVac": output_vac,
                                "outputHz": output_hz, "temperature": temp_c,
                                "batteryVoltage": v_batt, "lastBatteryVoltage": last_v,
                                "lastBatteryTimestamp": last_ts, "batterylevel": batt_level,
                                "loadPct": load_pct, "bateriaEmUso": em_uso,
                                "bateriaBaixa": batt_baixa, "watts": round(watts, 1),
                                "peakWatts": peak_watts, "currentA": round(current_a, 2),
                                "peakCurrent": peak_current, "minInputVac": min_vac,
                                "maxInputVac": max_vac, "online": True,
                                "timestamp": time.time(), "accumulated_kwh": dev.get('accumulated_kwh', 0)
                            }
                        }
                        prev_online = ENERGY_TELEMETRY.get(dev['id'], {}).get('telemetry', {}).get('online', True)
                        if not prev_online:
                            log_energy_event(dev['id'], "✔ Conexão NUT restabelecida")
                        # Sinaliza sync imediato se modo "na frequência dos dispositivos" (NUT)
                        if _sync_on_poll:
                            try: ENERGY_SYNC_QUEUE.put_nowait(dev['id'])
                            except: pass
                    except Exception as e:
                        if dev['id'] in ENERGY_TELEMETRY:
                            prev = ENERGY_TELEMETRY[dev['id']].get('telemetry', {})
                            if prev.get('online'):
                                log_energy_event(dev['id'], f"❌ Falha na conexão NUT: {e}")
                            ENERGY_TELEMETRY[dev['id']]['telemetry']['online'] = False
                
                # ── SENSORLINK ───────────────────────────────────────────
                elif integration == 'sensorlink':
                    host = dev.get('sensorlink_host', '')
                    if not host: continue
                    
                    try:
                        resp = requests.get(f"http://{host}/status", timeout=5)
                        if resp.status_code == 200:
                            data = resp.json()
                            tel = data.get('telemetry', {})
                            
                            ENERGY_TELEMETRY[dev['id']] = {
                                "success": True,
                                "telemetry": {
                                    "inputVac": float(tel.get('inputVac', 0)),
                                    "outputVac": float(tel.get('outputVac', 0)),
                                    "watts": float(tel.get('watts', 0)),
                                    "currentA": float(tel.get('currentA', 0)),
                                    "temperature": float(tel.get('temperature', 0)),
                                    "humidity": float(tel.get('humidity', 0)),
                                    "accumulated_kwh": float(tel.get('accumulated_kwh', 0)),
                                    "online": True,
                                    "timestamp": time.time(),
                                    "outputs": data.get('outputs', []),
                                    "inputs": data.get('inputs', [])
                                }
                            }
                            # Sinaliza sync imediato se modo "na frequência dos dispositivos" (SensorLink)
                            if _sync_on_poll:
                                try: ENERGY_SYNC_QUEUE.put_nowait(dev['id'])
                                except: pass
                            
                            if 'accumulated_kwh' in tel:
                                current_config = load_energy_config()
                                for c_dev in current_config:
                                    if str(c_dev.get('id')) == str(dev['id']):
                                        c_dev['accumulated_kwh'] = float(tel['accumulated_kwh'])
                                        dev['accumulated_kwh'] = c_dev['accumulated_kwh']
                                        break
                                save_energy_config(current_config)
                                
                            prev_online = ENERGY_TELEMETRY.get(dev['id'], {}).get('telemetry', {}).get('online', True)
                            if not prev_online:
                                log_energy_event(dev['id'], "✔ Conexão SensorLink restabelecida")
                        else:
                            raise Exception(f"Status code {resp.status_code}")
                    except Exception as e:
                        if dev['id'] in ENERGY_TELEMETRY:
                            prev = ENERGY_TELEMETRY[dev['id']].get('telemetry', {})
                            if prev.get('online'):
                                log_energy_event(dev['id'], f"❌ Falha na conexão SensorLink: {e}")
                            ENERGY_TELEMETRY[dev['id']]['telemetry']['online'] = False
                
                # ── TASMOTA ──────────────────────────────────────────────
                elif integration == 'tasmota':
                    host = dev.get('tasmota_host', '')
                    if not host: continue
                    
                    try:
                        resp = requests.get(f"http://{host}/cm?cmnd=Status%208", timeout=5)
                        if resp.status_code == 200:
                            data = resp.json()
                            energy = data.get('StatusSNS', {}).get('ENERGY', {})
                            
                            watts = float(energy.get('Power', 0))
                            volts = float(energy.get('Voltage', 0))
                            current = float(energy.get('Current', 0))
                            total = float(energy.get('Total', 0))
                            
                            ENERGY_TELEMETRY[dev['id']] = {
                                "success": True,
                                "telemetry": {
                                    "inputVac": volts,
                                    "watts": watts,
                                    "currentA": current,
                                    "accumulated_kwh": total,
                                    "online": True,
                                    "timestamp": time.time()
                                }
                            }
                            # Sinaliza sync imediato se modo "na frequência dos dispositivos" (Tasmota)
                            if _sync_on_poll:
                                try: ENERGY_SYNC_QUEUE.put_nowait(dev['id'])
                                except: pass
                            
                            if total > 0:
                                current_config = load_energy_config()
                                for c_dev in current_config:
                                    if str(c_dev.get('id')) == str(dev['id']):
                                        c_dev['accumulated_kwh'] = total
                                        dev['accumulated_kwh'] = total
                                        break
                                save_energy_config(current_config)
                                
                            prev_online = ENERGY_TELEMETRY.get(dev['id'], {}).get('telemetry', {}).get('online', True)
                            if not prev_online:
                                log_energy_event(dev['id'], "✔ Conexão Tasmota restabelecida")
                        else:
                            raise Exception(f"Status code {resp.status_code}")
                    except Exception as e:
                        if dev['id'] in ENERGY_TELEMETRY:
                            prev = ENERGY_TELEMETRY[dev['id']].get('telemetry', {})
                            if prev.get('online'):
                                log_energy_event(dev['id'], f"❌ Falha na conexão Tasmota: {e}")
                            ENERGY_TELEMETRY[dev['id']]['telemetry']['online'] = False
                
                # ── NOBREAK SERIAL ───────────────────────────────────────
                elif integration == 'nobreak':
                    port = dev.get('port', '')
                    if not port or port == 'auto': continue
                    lock = get_serial_lock(port)
                    if lock.locked(): continue
                    
                    try:
                        with lock:
                            with serial.Serial(port, baudrate=2400, timeout=1) as ser:
                                ser.write(bytearray.fromhex("51 ff ff ff ff b3 0d"))
                                response = ser.read(32)
                                respHex = binascii.hexlify(bytearray(response)).decode('utf-8')
                                print(f"[Energy Debug] Raw Hex: {respHex}")
                                
                                if len(respHex) >= 32 and respHex.startswith('3d'):
                                    # Parsing dos valores
                                    input_vac = int(respHex[6:10], 16) / 10.0
                                    output_vac = int(respHex[10:14], 16) / 10.0
                                    out_power_pct = int(respHex[14:18], 16) / 10.0
                                    output_hz = int(respHex[18:22], 16) / 10.0
                                    batt_level = int(respHex[22:26], 16) / 10.0
                                    temp_c = int(respHex[26:30], 16) / 10.0
                                    status_byte = int(respHex[30:32], 16)
                                    bi = "{0:08b}".format(status_byte)

                                    # Tenta encontrar a tensão da bateria em 3 lugares (varia por modelo SMS)
                                    v_batt = None
                                    prev_tel = ENERGY_TELEMETRY.get(dev['id'], {}).get('telemetry', {})
                                    if prev_tel.get('online') is False:
                                        log_energy_event(dev['id'], "✔ Conexão restabelecida com o Nobreak")
                                    
                                    pos_possiveis = [(2,6), (32,36), (36,40)]
                                    for start, end in pos_possiveis:
                                        if len(respHex) >= end:
                                            try:
                                                val = int(respHex[start:end], 16) / 10.0
                                                # Faixa ampliada: 10V a 35V (cobre bancos de 12V e 24V carregando)
                                                if 10.0 < val < 35.0:
                                                    v_batt = val
                                                    break
                                            except: continue
                                    
                                    # Guarda o último valor válido e quando ele veio
                                    last_v = prev_tel.get('lastBatteryVoltage')
                                    last_ts = prev_tel.get('lastBatteryTimestamp')
                                    
                                    if v_batt is not None:
                                        last_v = v_batt
                                        last_ts = time.time()
                                    
                                    # Detectar Eventos de Rede
                                    em_uso = bi[0] == '1'
                                    prev = ENERGY_TELEMETRY.get(dev['id'], {}).get('telemetry', {})
                                    if em_uso and not prev.get('bateriaEmUso'):
                                        log_energy_event(dev['id'], "⚠ REDE CAIU: Operando por bateria")
                                    elif not em_uso and prev.get('bateriaEmUso'):
                                        log_energy_event(dev['id'], "✔ REDE VOLTOU: Carregando baterias")
                                    
                                    # Estimativa de Watts usando VA e Fator de Potência
                                    nominal_va = dev.get('nominal_va', 1800.0)
                                    fp = dev.get('power_factor', 0.7)
                                    watts = (out_power_pct / 100.0) * (nominal_va * fp)
                                    
                                    # Cálculo de Corrente (A) = W / V
                                    current_a = watts / output_vac if output_vac > 50 else 0
                                    
                                    # Picos e Extremos da Sessão (Em Memória)
                                    peak_watts = max(round(watts, 1), prev.get('peakWatts', 0))
                                    peak_current = max(round(current_a, 2), prev.get('peakCurrent', 0))
                                    
                                    min_vac = prev.get('minInputVac', input_vac)
                                    max_vac = prev.get('maxInputVac', input_vac)
                                    
                                    if input_vac > 50: # Evita registrar 0V em quedas de rede
                                        if min_vac < 50 or input_vac < min_vac:
                                            min_vac = input_vac
                                        if input_vac > max_vac:
                                            max_vac = input_vac
                                    
                                    hours = dt / 3600.0
                                    kwh_gain = (watts * hours) / 1000.0
                                    
                                    # Atualiza o arquivo de forma atômica para evitar sobrepor o reset
                                    current_config = load_energy_config()
                                    for c_dev in current_config:
                                        if str(c_dev.get('id')) == str(dev['id']):
                                            c_dev['accumulated_kwh'] = c_dev.get('accumulated_kwh', 0.0) + kwh_gain
                                            dev['accumulated_kwh'] = c_dev['accumulated_kwh'] # Atualiza referência local
                                            break
                                    save_energy_config(current_config)
                                    
                                    ENERGY_TELEMETRY[dev['id']] = {
                                        "success": True,
                                        "telemetry": {
                                            "inputVac": input_vac,
                                            "outputVac": output_vac,
                                            "outputHz": output_hz,
                                            "temperature": temp_c,
                                            "batteryVoltage": v_batt,
                                            "lastBatteryVoltage": last_v,
                                            "lastBatteryTimestamp": last_ts,
                                            "batterylevel": batt_level,
                                            "loadPct": out_power_pct,
                                            "bateriaEmUso": em_uso,
                                            "bateriaBaixa": bi[1] == '1',
                                            "watts": round(watts, 1),
                                            "peakWatts": peak_watts,
                                            "currentA": round(current_a, 2),
                                            "peakCurrent": peak_current,
                                            "minInputVac": min_vac,
                                            "maxInputVac": max_vac,
                                            "online": True,
                                            "timestamp": time.time(),
                                            "raw": respHex
                                        }
                                    }
                                    # Sinaliza sync imediato se modo "na frequência dos dispositivos"
                                    if load_sync_config().get('sync_on_device_poll'):
                                        try: ENERGY_SYNC_QUEUE.put_nowait(dev['id'])
                                        except: pass
                    except Exception as e:
                        if dev['id'] in ENERGY_TELEMETRY:
                            prev = ENERGY_TELEMETRY[dev['id']].get('telemetry', {})
                            if prev.get('online'):
                                log_energy_event(dev['id'], f"❌ Conexão perdida com o Nobreak: {e}")
                            ENERGY_TELEMETRY[dev['id']]['telemetry']['online'] = False
            

        except Exception as e:
            log_error(f"Erro no loop de energia: {e}")
            
        time.sleep(1) # Verifica a cada 1 segundo

def load_token():
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, 'r') as f:
                return json.load(f).get('token', '')
        except:
            return ''
    return ''

def save_token_file(token):
    with open(AUTH_FILE, 'w') as f:
        json.dump({'token': token}, f)

def refresh_cloud_metadata(token):
    global CLOUD_METADATA
    now = time.time()
    if now - CLOUD_METADATA['last_refresh'] < 60: return
    
    headers = {'x-device-token': token}
    base_url = "https://iwsqfjngeicyrcdowdbi.supabase.co/functions/v1/device-api"
    
    try:
        # Get User ID
        auth_resp = requests.get(f"{base_url}/auth", headers=headers, timeout=5)
        if auth_resp.status_code == 200:
            data = auth_resp.json()
            if data.get('success'):
                d = data.get('data', {})
                CLOUD_METADATA['user_id'] = d.get('id') or d.get('user_id') or d.get('email')
        
        # Get Machines list (sync_code -> machine_id)
        m_resp = requests.get(f"{base_url}/hub/machines", headers=headers, timeout=5)
        if m_resp.status_code == 200:
            m_data = m_resp.json()
            if m_data.get('success'):
                machines = {}
                for m in m_data.get('data', []):
                    code = m.get('sync_code')
                    mid = m.get('id') or m.get('machine_id')
                    if code: machines[code] = mid
                CLOUD_METADATA['machines'] = machines
        
        CLOUD_METADATA['last_refresh'] = now
    except Exception as e:
        log_error(f"Erro ao atualizar metadados cloud: {e}")


def update_printers_once():
    global PRINTERS
    current_config = load_config()
    
    if current_config is None:
        return

    config_map = {str(p['id']): p for p in current_config}
    
    with PRINTERS_LOCK:
        printers_copy = list(PRINTERS)
    
    # Remove deleted printers
    for p in printers_copy:
        pid = str(p.config['id'])
        if pid not in config_map:
            try: p.stop()
            except: pass
            if pid in STATUS_CACHE:
                del STATUS_CACHE[pid]
                
    with PRINTERS_LOCK:
        PRINTERS[:] = [p for p in PRINTERS if str(p.config['id']) in config_map]
        current_ids = [str(p.config['id']) for p in PRINTERS]
        
        for p_conf in current_config:
            if str(p_conf['id']) not in current_ids:
                new_p = create_printer_from_config(p_conf)
                if new_p:
                    PRINTERS.append(new_p)
            else:
                for p in PRINTERS:
                    if str(p.config['id']) == str(p_conf['id']):
                        p.config = p_conf
                        p.ip = p_conf.get('ip')
                        break
        
        id_to_pos = {str(p['id']): i for i, p in enumerate(current_config)}
        PRINTERS.sort(key=lambda p: id_to_pos.get(str(p.config['id']), 999))

def update_p(p):
    try:
        if not p.config.get('enabled', True):
            s = p.get_status()
            s['state'] = 'off'
            STATUS_CACHE[p.config['id']] = s
            return
        p.update()
        
        # Otimização: Captura snapshot em segundo plano se não houver thread dedicada (ex: Bambu)
        if hasattr(p, 'get_snapshot') and not hasattr(p, 'cam_thread'):
            now = time.time()
            # Respeita o intervalo definido pelo usuário em 'refresh_interval' (em ms)
            interval_sec = p.config.get('refresh_interval', 5000) / 1000.0
            # Garanto que pelo menos a cada X segundos ele tente atualizar o frame no buffer
            if now - getattr(p, '_last_snapshot_time', 0) >= interval_sec or not p.last_frame:
                p._last_snapshot_time = now
                frame = p.get_snapshot()
                if frame:
                    p.last_frame = frame

        STATUS_CACHE[p.config['id']] = p.get_status()
    except Exception as e:
        log_error(f"Update failed for {p.config.get('name')}: {e}")

def polling_loop():
    while KEEP_RUNNING:
        try:
            update_printers_once()
            if not KEEP_RUNNING: break
            
            with PRINTERS_LOCK:
                printers_snap = list(PRINTERS)
                
            for p in printers_snap:
                if not KEEP_RUNNING: break
                try:
                    executor.submit(update_p, p)
                except RuntimeError:
                    break
            time.sleep(2)
        except Exception as e:
            if KEEP_RUNNING:
                log_error(f"Error in polling loop: {e}")
            time.sleep(5)

def signal_handler(sig, frame):
    global KEEP_RUNNING
    log_info("\n[System] Encerrando serviços (Aguarde)...")
    KEEP_RUNNING = False
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except: pass
    
    with PRINTERS_LOCK:
        printers_to_stop = list(PRINTERS)
        
    for p in printers_to_stop:
        try: p.stop()
        except: pass
    print("[System] Finalizado.")
    os._exit(0)

signal.signal(signal.SIGINT, signal_handler)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/monitor')
def monitor():
    return render_template('monitor.html')

@app.route('/energy')
def energy_page():
    return render_template('energy.html')

@app.route('/docs/sensorlink')
def docs_sensorlink():
    return render_template('docs_sensorlink.html')

@app.route('/console')
def console_page():
    return render_template('console.html')

@app.route('/auth')
@app.route('/configuracoes')
def auth():
    return render_template('auth.html')

@app.route('/api/logs')
def get_logs():
    try:
        raw_id = request.args.get('last_id', '0')
        last_id = int(raw_id) if raw_id and raw_id.isdigit() else 0
        new_logs = [log for log in LOG_BUFFER if log['id'] > last_id]
        return jsonify(new_logs)
    except:
        return jsonify([])

@app.route('/api/auth/profile', methods=['GET'])
def get_profile():
    token = load_token()
    if not token:
        return jsonify({'success': False, 'message': 'Token missing'})
    
    try:
        import requests
        base_url = "https://iwsqfjngeicyrcdowdbi.supabase.co/functions/v1/device-api"
        headers = {'x-device-token': token}
        resp = requests.get(f"{base_url}/auth", headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return jsonify({
                'success': True,
                'data': data.get('data', {}),
                'token_raw': token # Explicitly requested not masked
            })
        return jsonify({'success': False, 'status_code': resp.status_code})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/system_stats')
def system_stats():
    global LAST_PROC_IO, LAST_PROC_TIME
    
    # Process specific stats
    process = psutil.Process(os.getpid())
    
    # App CPU & Memory
    app_cpu = process.cpu_percent(interval=None) / psutil.cpu_count()
    mem_info = process.memory_info()
    app_mem_bytes = mem_info.rss
    
    # App I/O Rate Calculation (Proxy for Net/Disk Activity)
    read_speed = 0
    write_speed = 0
    total_io_bytes = 0
    try:
        current_io = process.io_counters()
        current_time = time.time()
        
        # Total Accumulated
        total_io_bytes = current_io.read_bytes + current_io.write_bytes
        
        if LAST_PROC_IO and LAST_PROC_TIME:
            duration = current_time - LAST_PROC_TIME
            if duration > 0:
                read_speed = (current_io.read_bytes - LAST_PROC_IO.read_bytes) / duration
                write_speed = (current_io.write_bytes - LAST_PROC_IO.write_bytes) / duration
        
        LAST_PROC_IO = current_io
        LAST_PROC_TIME = current_time
    except Exception as e:
        # io_counters might not be available on all platforms
        pass

    # System metrics
    sys_cpu = psutil.cpu_percent(interval=None)
    sys_mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    net = psutil.net_io_counters()

    return jsonify({
        'app': {
            'cpu': round(app_cpu, 2),
            'memory_bytes': app_mem_bytes,
            'memory_percent': round(process.memory_percent(), 2),
            'io_read_speed': round(read_speed, 2),
            'io_write_speed': round(write_speed, 2),
            'io_read_bytes': current_io.read_bytes,
            'io_write_bytes': current_io.write_bytes,
            'uptime_seconds': int(time.time() - APP_START_TIME)
        },
        'system': {
            'cpu': sys_cpu,
            'memory_percent': sys_mem.percent,
            'memory_used_bytes': sys_mem.used,
            'memory_total_bytes': sys_mem.total,
            'disk_percent': disk.percent,
            'disk_used_bytes': disk.used,
            'disk_total_bytes': disk.total,
            'net_sent_bytes': net.bytes_sent,
            'net_recv_bytes': net.bytes_recv
        }
    })

@app.route('/api/save_token', methods=['POST'])
def save_token_api():
    token = request.json.get('token')
    save_token_file(token)
    return jsonify({'success': True})

@app.route('/api/get_token', methods=['GET'])
def get_token_api():
    token = load_token()
    masked = token
    return jsonify({'token': masked})

@app.route('/api/backup', methods=['GET'])
def backup_config():
    """Gera um backup completo: config.json + auth_token.json"""
    try:
        printers = load_config() or []
        token = load_token()
        backup = {
            'backup_version': '1',
            'created_at': datetime.now().isoformat(),
            'app_version': open('VERSION').read().strip() if os.path.exists('VERSION') else 'dev',
            'auth_token': token or None,
            'printers': printers
        }
        return jsonify({'success': True, 'backup': backup})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/restore', methods=['POST'])
def restore_config():
    """Restaura backup: escreve config.json e auth_token.json"""
    try:
        data = request.json
        if not data or data.get('backup_version') != '1':
            return jsonify({'success': False, 'message': 'Arquivo de backup inválido ou versão incompatível'}), 400

        # Restaurar impressoras
        printers = data.get('printers', [])
        if not isinstance(printers, list):
            return jsonify({'success': False, 'message': 'Campo printers inválido'}), 400
        save_config(printers)

        # Restaurar token
        token = data.get('auth_token')
        token_restored = False
        if token:
            save_token_file(token)
            token_restored = True

        # Recarregar impressoras em memória
        global PRINTERS
        with PRINTERS_LOCK:
            printers_old = list(PRINTERS)
        for pr in printers_old:
            try: pr.stop()
            except: pass
            
        with PRINTERS_LOCK:
            PRINTERS.clear()
        update_printers_once()

        log_info(f"[System] Backup restaurado: {len(printers)} impressoras, token={'sim' if token_restored else 'não'}")
        return jsonify({'success': True, 'printers_restored': len(printers), 'token_restored': token_restored})
    except Exception as e:
        log_error(f"[System] Erro ao restaurar backup: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/printers', methods=['GET'])
def get_printers():
    # Return printers in the order of the PRINTERS list (which matches config)
    ordered_status = []
    with PRINTERS_LOCK:
        printers_list = list(PRINTERS)
        
    for p in printers_list:
        pid = p.config['id']
        if pid in STATUS_CACHE:
            ordered_status.append(STATUS_CACHE[pid])
        else:
            # Fallback if not updated yet
            ordered_status.append(p.get_status())
    return jsonify(ordered_status)

@app.route('/api/camera/<printer_id>', methods=['GET'])
def get_camera_frame(printer_id):
    with PRINTERS_LOCK:
        printer = next((p for p in PRINTERS if str(p.config['id']) == str(printer_id)), None)
    if printer:
        # Priorizar frame do buffer (Bambu, Klipper em background, Elegoo em background) muito mais estável
        if hasattr(printer, 'last_frame') and printer.last_frame:
            from flask import Response
            return Response(printer.last_frame, mimetype='image/jpeg')
        
        # Fallback apenas se o buffer estiver vazio mas houver método de snapshot
        if hasattr(printer, 'get_snapshot'):
            frame = printer.get_snapshot()
            if frame:
                from flask import Response
                return Response(frame, mimetype='image/jpeg')
                
    return jsonify({'error': 'No frame available'}), 404

@app.route('/api/raw_status/<printer_id>', methods=['GET'])
def raw_status(printer_id):
    with PRINTERS_LOCK:
        printer = next((p for p in PRINTERS if str(p.config['id']) == str(printer_id)), None)
    if printer:
        return jsonify({
            'config': printer.config,
            'status': printer.status,
            'last_update': printer.last_update
        })
    return jsonify({'error': 'Printer not found'}), 404

@app.route('/api/bambu/files/<printer_id>', methods=['GET'])
def get_bambu_files(printer_id):
    category = request.args.get('category', 'files')
    subpath = request.args.get('path', None)
    with PRINTERS_LOCK:
        printer = next((p for p in PRINTERS if str(p.config['id']) == str(printer_id)), None)
    if printer and hasattr(printer, 'list_bambu_files'):
        files = printer.list_bambu_files(category=category, path=subpath)
        return jsonify({'success': True, 'files': files})
    return jsonify({'success': False, 'error': 'Printer not found or not a Bambu printer'}), 404

@app.route('/api/bambu/delete_file', methods=['POST'])
def delete_bambu_file():
    data = request.json
    p_id = data.get('id')
    path = data.get('path')
    with PRINTERS_LOCK:
        printer = next((p for p in PRINTERS if str(p.config['id']) == str(p_id)), None)
    if printer and hasattr(printer, 'delete_bambu_file'):
        success = printer.delete_bambu_file(path)
        return jsonify({'success': success})
    return jsonify({'success': False, 'error': 'Not supported'}), 404

@app.route('/api/bambu/download_file', methods=['GET'])
def download_bambu_file():
    p_id = request.args.get('id')
    path = request.args.get('path')
    action = request.args.get('action', 'download')
    with PRINTERS_LOCK:
        printer = next((p for p in PRINTERS if str(p.config['id']) == str(p_id)), None)
    
    if printer:
        filename = path.split('/')[-1]
        mimetype = 'application/octet-stream'
        if filename.lower().endswith('.mp4'):
            mimetype = 'video/mp4'
        elif filename.lower().endswith('.avi'):
            mimetype = 'video/x-msvideo'
        
        def generate_ftp_stream():
            import ssl
            from printer_drivers import ImplicitFTP_TLS
            import queue
            import threading
            
            q = queue.Queue(maxsize=15)
            worker_thread = threading.current_thread()
            
            def worker():
                try:
                    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    
                    ftp = ImplicitFTP_TLS(context=context)
                    ftp.connect(printer.ip, 990, timeout=10)
                    ftp.login("bblp", printer.access_code)
                    ftp.prot_p()
                    
                    def callback(chunk):
                        if getattr(worker_thread, "abort_ftp", False):
                            raise Exception("Client disconnected")
                        q.put(chunk)
                        
                    ftp.retrbinary(f"RETR {path}", callback, 16384)
                    ftp.quit()
                except Exception as e:
                    pass
                finally:
                    q.put(None)

            t = threading.Thread(target=worker)
            t.daemon = True
            t.start()
            
            try:
                while True:
                    chunk = q.get(timeout=30)
                    if chunk is None:
                        break
                    yield chunk
            except GeneratorExit:
                # O cliente fechou a conexão ou parou o vídeo
                worker_thread.abort_ftp = True
        
        headers = {}
        if action == 'download':
            headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        else:
            headers['Content-Disposition'] = 'inline'
            
        from flask import Response, stream_with_context
        return Response(stream_with_context(generate_ftp_stream()), mimetype=mimetype, headers=headers)
        
    return "Printer not found", 404

@app.route('/api/add_printer', methods=['POST'])
def add_printer():
    data = request.json
    config = load_config()
    new_id = str(int(time.time()))
    new_printer = {
        'id': new_id,
        'name': data.get('name'),
        'type': data.get('type'),
        'ip': data.get('ip'),
        'port': int(data.get('port', 80)),
        'serial': data.get('serial', ''),
        'access_code': data.get('access_code', ''),
        'camera_url': data.get('camera_url', ''),
        'custom_camera': data.get('custom_camera', False),
        'camera_refresh': data.get('camera_refresh', False),
        'refresh_interval': int(data.get('refresh_interval', 5000)),
        'platform_token': data.get('platform_token', ''),
        'enabled': True,
        'total_usage': data.get('total_usage', 0.0),
        'ignore_unknown_hms': data.get('ignore_unknown_hms', True)
    }
    if new_printer['type'] == 'elegoo':
        new_printer['port'] = 3000
    config.append(new_printer)
    save_config(config)
    return jsonify({"success": True, "id": new_id})

@app.route('/api/update_printer', methods=['POST'])
def update_printer():
    data = request.json
    p_id = data.get('id')
    config = load_config()
    for p in config:
        if p['id'] == p_id:
            p['name'] = data.get('name', p['name'])
            p['type'] = data.get('type', p['type'])
            p['ip'] = data.get('ip', p['ip'])
            p['serial'] = data.get('serial', p.get('serial', ''))
            p['camera_url'] = data.get('camera_url', p.get('camera_url', ''))
            p['custom_camera'] = data.get('custom_camera', p.get('custom_camera', False))
            p['camera_refresh'] = data.get('camera_refresh', p.get('camera_refresh', False))
            p['refresh_interval'] = int(data.get('refresh_interval', p.get('refresh_interval', 5000)))
            p['access_code'] = data.get('access_code', p.get('access_code', ''))
            p['platform_token'] = data.get('platform_token', p.get('platform_token', ''))
            p['total_usage'] = float(data.get('total_usage', p.get('total_usage', 0.0)))
            p['ignore_unknown_hms'] = data.get('ignore_unknown_hms', True)
            if p['type'] == 'elegoo':
                p['port'] = 3000
            else:
                p['port'] = int(data.get('port', p.get('port', 80)))
            break
    save_config(config)
    global PRINTERS
    with PRINTERS_LOCK:
        printers_to_stop = [pr for pr in PRINTERS if str(pr.config['id']) == str(p_id)]
    
    for pr in printers_to_stop:
        try: pr.stop()
        except: pass
        
    with PRINTERS_LOCK:
        PRINTERS[:] = [pr for pr in PRINTERS if str(pr.config['id']) != str(p_id)]
    update_printers_once()
    return jsonify({"success": True})

@app.route('/api/toggle_printer', methods=['POST'])
def toggle_printer():
    p_id = request.json.get('id')
    config = load_config()
    for p in config:
        if p['id'] == p_id:
            p['enabled'] = not p.get('enabled', True)
            break
    save_config(config)
    for pr in PRINTERS:
        if pr.config['id'] == p_id:
            is_enabled = not pr.config.get('enabled', True)
            pr.config['enabled'] = is_enabled
            # Shutdown or Startup background tasks immediately
            if not is_enabled:
                log_info(f"[System] Desativando impressora {pr.name}...")
                pr.stop()
            else:
                log_info(f"[System] Reativando impressora {pr.name}...")
                try: pr.connect()
                except: pass
            
            # Update cache immediately for frontend responsiveness
            STATUS_CACHE[p_id] = pr.get_status()
            break
    return jsonify({"success": True})

@app.route('/api/machine_action', methods=['POST'])
def machine_action():
    data = request.json
    p_id = data.get('id')
    action = data.get('action')
    with PRINTERS_LOCK:
        printer = next((p for p in PRINTERS if str(p.config['id']) == str(p_id)), None)
    if printer and action:
        printer.send_command(action)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Printer not found or empty action"}), 404

@app.route('/api/gcode', methods=['POST'])
def send_gcode():
    data = request.json
    p_id = data.get('id')
    gcode = data.get('gcode', '')
    printer = next((p for p in PRINTERS if p.config['id'] == p_id), None)
    if printer and gcode:
        printer.send_command('gcode', gcode=gcode)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Printer not found or empty gcode"}), 404

@app.route('/api/delete_printer', methods=['POST'])
def delete_printer():
    data = request.json
    p_id = data.get('id')
    config = load_config()
    new_config = []
    for p in config:
        if str(p['id']) != str(p_id):
            new_config.append(p)
    save_config(new_config)
    
    global PRINTERS
    with PRINTERS_LOCK:
        printers_to_stop = [pr for pr in PRINTERS if str(pr.config['id']) == str(p_id)]
        
    for pr in printers_to_stop:
        try: pr.stop()
        except: pass
        
    with PRINTERS_LOCK:
        PRINTERS[:] = [pr for pr in PRINTERS if str(pr.config['id']) != str(p_id)]
    
    if p_id in STATUS_CACHE:
        del STATUS_CACHE[p_id]
    update_printers_once()
    return jsonify({"success": True})

@app.route('/api/energy_devices', methods=['GET'])
def get_energy_devices():
    return jsonify(load_energy_config())

@app.route('/api/energy_devices', methods=['POST'])
def add_energy_device():
    data = request.json
    config = load_energy_config()
    new_device = {
        'id': str(int(time.time())),
        'name': data.get('name'),
        'code': data.get('code', ''),
        'integration': data.get('integration'),
        'brand': data.get('brand', ''),
        'port': data.get('port', ''),
        'nut_host': data.get('nut_host', ''),
        'nut_port': int(data.get('nut_port', 3493)),
        'nut_ups_name': data.get('nut_ups_name', 'ups'),
        'nut_user': data.get('nut_user', ''),
        'nut_password': data.get('nut_password', ''),
        'sensorlink_host': data.get('sensorlink_host', ''),
        'tasmota_host': data.get('tasmota_host', ''),
        'associatedIds': data.get('associatedIds', []),
        'associatedNames': data.get('associatedNames', []),
        'nominal_va': float(data.get('nominal_va', 1800.0)),
        'power_factor': float(data.get('power_factor', 0.7)),
        'polling_interval': float(data.get('polling_interval', 3.0))
    }
    config.append(new_device)
    save_energy_config(config)
    return jsonify({"success": True, "device": new_device})

@app.route('/api/energy_devices/<device_id>', methods=['PUT'])
def update_energy_device(device_id):
    data = request.json
    config = load_energy_config()
    for d in config:
        if str(d.get('id')) == str(device_id):
            d['name'] = data.get('name', d['name'])
            d['code'] = data.get('code', d.get('code', ''))
            d['integration'] = data.get('integration', d['integration'])
            d['brand'] = data.get('brand', d.get('brand', ''))
            d['port'] = data.get('port', d.get('port', ''))
            d['nut_host'] = data.get('nut_host', d.get('nut_host', ''))
            d['nut_port'] = int(data.get('nut_port', d.get('nut_port', 3493)))
            d['nut_ups_name'] = data.get('nut_ups_name', d.get('nut_ups_name', 'ups'))
            d['nut_user'] = data.get('nut_user', d.get('nut_user', ''))
            d['nut_password'] = data.get('nut_password', d.get('nut_password', ''))
            d['sensorlink_host'] = data.get('sensorlink_host', d.get('sensorlink_host', ''))
            d['tasmota_host'] = data.get('tasmota_host', d.get('tasmota_host', ''))
            d['associatedIds'] = data.get('associatedIds', d.get('associatedIds', []))
            d['associatedNames'] = data.get('associatedNames', d.get('associatedNames', []))
            d['nominal_va'] = float(data.get('nominal_va', d.get('nominal_va', 1800.0)))
            d['power_factor'] = float(data.get('power_factor', d.get('power_factor', 0.7)))
            d['polling_interval'] = float(data.get('polling_interval', d.get('polling_interval', 3.0)))
            break
    save_energy_config(config)
    return jsonify({"success": True})

@app.route('/api/energy_devices/<device_id>', methods=['DELETE'])
def delete_energy_device(device_id):
    config = load_energy_config()
    new_config = [d for d in config if str(d.get('id')) != str(device_id)]
    save_energy_config(new_config)
    return jsonify({"success": True})

@app.route('/api/energy_devices/<device_id>/reset', methods=['POST'])
def reset_energy_consumption(device_id):
    config = load_energy_config()
    changed = False
    for d in config:
        if str(d.get('id')) == str(device_id):
            d['accumulated_kwh'] = 0.0
            d['peak_watts'] = 0.0
            d['peak_current'] = 0.0
            changed = True
            break
    if changed:
        save_energy_config(config)
    return jsonify({"success": True})

@app.route('/api/system/ports', methods=['GET'])
def get_system_ports():
    try:
        import serial.tools.list_ports
        ports = [p.device for p in serial.tools.list_ports.comports()]
        return jsonify({"success": True, "ports": ports})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/energy_devices/<device_id>/status', methods=['GET'])
def get_energy_device_status(device_id):
    config = load_energy_config()
    device = next((d for d in config if str(d.get('id')) == str(device_id)), None)
    if not device:
        return jsonify({"success": False, "error": "Device not found"})

    cached = ENERGY_TELEMETRY.get(str(device_id))
    if cached:
        res = cached.copy()
        res['telemetry']['accumulated_kwh'] = round(device.get('accumulated_kwh', 0.0), 6)
        return jsonify(res)
        
    return jsonify({"success": False, "error": "Aguardando leitura..."})

@app.route('/api/energy_devices/<device_id>/logs', methods=['GET'])
def get_energy_device_logs(device_id):
    return jsonify(ENERGY_LOGS.get(str(device_id), []))

@app.route('/api/energy_devices/<device_id>/logs', methods=['DELETE'])
def delete_energy_device_logs(device_id):
    if str(device_id) in ENERGY_LOGS:
        ENERGY_LOGS[str(device_id)] = []
        save_energy_logs()
    return jsonify({"success": True})

@app.route('/api/energy_devices/<device_id>/command', methods=['POST'])
def send_energy_device_command(device_id):
    data = request.json
    cmd_type = data.get('cmd')
    
    config = load_energy_config()
    device = next((d for d in config if str(d.get('id')) == str(device_id)), None)
    if not device:
        return jsonify({"success": False, "error": "Device not found"})

    if device.get('integration') == 'nobreak':
        port = device.get('port')
        if not port or port == 'auto':
            return jsonify({"success": False, "error": "Porta inválida"})
            
        cmds_map = {
            'T': "54 00 10 00 00 9c 0d", # Teste 10s
            'T60': "54 00 3C 00 00 70 0d", # Teste 60s (1m)
            'M': "4d ff ff ff ff b7 0d", # Beep
            'R': "52 00 C8 27 0F B0 0D", # Shutdown
            'C': "43 ff ff ff ff c1 0d"  # Cancel/On (Se estiver em shutdown timer)
        }
        
        hex_cmd = cmds_map.get(cmd_type)
        if not hex_cmd:
            return jsonify({"success": False, "error": "Comando desconhecido"})
            
        try:
            import serial
            import time
            lock = get_serial_lock(port)
            with lock:
                with serial.Serial(port, baudrate=2400, timeout=1.5) as ser:
                    cmd_bytes = bytearray.fromhex(hex_cmd)
                    for cmd_byte in cmd_bytes:
                        ser.write(bytearray([cmd_byte]))
                        time.sleep(.050)
            
            cmd_names = {'T': 'Teste de Bateria', 'T60': 'Teste de Bateria (1m)', 'M': 'Toggle Beep', 'R': 'Forçar Desligamento', 'C': 'Cancelar/Ligar'}
            log_energy_event(str(device_id), f"⌨ COMANDO: {cmd_names.get(cmd_type, cmd_type)}")
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    elif device.get('integration') == 'tasmota':
        host = device.get('tasmota_host')
        if not host:
            return jsonify({"success": False, "error": "Host inválido"})
            
        tasmota_cmd = f"Power {cmd_type}"
            
        try:
            import requests
            resp = requests.get(f"http://{host}/cm?cmnd={tasmota_cmd}", timeout=5)
            if resp.status_code == 200:
                log_energy_event(str(device_id), f"⌨ COMANDO: {tasmota_cmd}")
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": f"Status code {resp.status_code}"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    return jsonify({"success": False, "error": "Não suportado"})

@app.route('/api/reorder_printers', methods=['POST'])
def reorder_printers():
    p_id = request.json.get('id')
    direction = request.json.get('direction') # 'up' or 'down'
    config = load_config()
    
    idx = next((i for i, p in enumerate(config) if p['id'] == p_id), -1)
    if idx == -1: return jsonify({"success": False}), 404
    
    if direction == 'up' and idx > 0:
        config[idx], config[idx-1] = config[idx-1], config[idx]
    elif direction == 'down' and idx < len(config) - 1:
        config[idx], config[idx+1] = config[idx+1], config[idx]
    
    save_config(config)
    update_printers_once()
    return jsonify({"success": True})

@app.route('/api/control', methods=['POST'])
def control_printer():
    data = request.json
    p_id = data.get('id')
    command = data.get('command')
    val = data.get('val', None)

    printer = next((p for p in PRINTERS if p.config['id'] == p_id), None)
    if printer:
        kwargs = {}
        if isinstance(val, dict):
            kwargs = val
        elif val is not None:
            kwargs['val'] = val
        
        log_info(f"Command '{command}' sent to {printer.name}")
        printer.send_command(command, **kwargs)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Printer not found"}), 404

@app.route('/api/auth/verify', methods=['GET'])
def verify_auth():
    token = load_token()
    if not token:
        return jsonify({'success': False, 'message': 'Token missing'})
    
    try:
        import requests
        base_url = "https://iwsqfjngeicyrcdowdbi.supabase.co/functions/v1/device-api"
        headers = {'x-device-token': token}
        resp = requests.get(f"{base_url}/auth", headers=headers, timeout=5)
        if resp.status_code == 200:
            return jsonify(resp.json())
        return jsonify({'success': False, 'status_code': resp.status_code, 'data': resp.text})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sync_settings', methods=['GET'])
def get_sync_settings():
    return jsonify(load_sync_config())

@app.route('/api/sync_settings', methods=['POST'])
def save_sync_settings():
    data = request.json
    cfg = {
        'sync_interval_s': max(1, int(data.get('sync_interval_s', 5))),
        'sync_on_device_poll': bool(data.get('sync_on_device_poll', False))
    }
    save_sync_config(cfg)
    return jsonify({'success': True, 'config': cfg})

def _sync_one_energy_device(dev, session, headers, base_url):
    """Sincroniza um único dispositivo de energia com a plataforma remota."""
    sync_code = dev.get('code')
    if not sync_code: return

    tel_data = ENERGY_TELEMETRY.get(dev['id'], {})
    if not tel_data.get('success'): return

    tel = tel_data.get('telemetry', {})

    # ── accumulated_kwh vem do config do dispositivo (fonte da verdade persistida)
    accumulated_kwh = round(float(dev.get('accumulated_kwh', 0.0)), 6)

    # ── data: apenas campos limpos e relevantes para a plataforma
    data_obj = {
        "mode": "battery" if tel.get('bateriaEmUso') else "grid",
        "online":         tel.get('online', True),
        "inputVac":       tel.get('inputVac', 0),
        "outputVac":      tel.get('outputVac', 0),
        "outputHz":       round(tel.get('outputHz', 0), 1),
        "loadPct":        tel.get('loadPct', 0),
        "watts":          tel.get('watts', 0),
        "peakWatts":      tel.get('peakWatts', 0),
        "currentA":       tel.get('currentA', 0),
        "peakCurrent":    tel.get('peakCurrent', 0),
        "batterylevel":   tel.get('batterylevel', 0),
        "bateriaEmUso":   tel.get('bateriaEmUso', False),
        "bateriaBaixa":   tel.get('bateriaBaixa', False),
        "temperature":    tel.get('temperature', 0),
        "accumulated_kwh": accumulated_kwh,
    }
    # Campos opcionais (só envia se tiver valor válido)
    if tel.get('batteryVoltage') is not None:
        data_obj["batteryVoltage"] = tel['batteryVoltage']
    if tel.get('humidity', 0):
        data_obj["humidity"] = tel['humidity']
    if tel.get('minInputVac') is not None:
        data_obj["minInputVac"] = tel['minInputVac']
    if tel.get('maxInputVac') is not None:
        data_obj["maxInputVac"] = tel['maxInputVac']

    # ── Preencher associated_devices
    assoc_list = []
    associated_ids = dev.get('associatedIds', [])
    if associated_ids:
        with PRINTERS_LOCK:
            for pid in associated_ids:
                pr = next((p for p in PRINTERS if str(p.config['id']) == str(pid)), None)
                if pr and pr.config.get('platform_token'):
                    assoc_list.append({
                        "platform_token": pr.config.get('platform_token'),
                        "name": pr.name if hasattr(pr, 'name') else pr.config.get('name', 'Printer')
                    })

    payload = {
        "platform_token": sync_code,
        "name": dev.get('name', 'Energy Device'),
        "integration": {
            "type":              dev.get('integration', 'unknown'),
            "brand":             dev.get('brand', ''),
            "port":              dev.get('port', ''),
            "polling_interval_s": dev.get('polling_interval', 1),
            "nominal_va":        dev.get('nominal_va', 1800),
            "power_factor":      dev.get('power_factor', 0.7),
        },
        "associated_devices": assoc_list,
        "timestamp": time.time(),
        "data": data_obj,
    }

    log_cloud(f"Sincronizando Dispositivo Energia {dev['name']}")

    try:
        sync_resp = session.post(f"{base_url}/energy/sync", headers=headers, json=payload, timeout=5)
        if sync_resp.status_code != 200:
            log_warn(f"Erro Cloud Energia ({dev['name']}): Status {sync_resp.status_code} - {sync_resp.text[:120]}")
    except Exception as e:
        log_warn(f"Erro Cloud Energia ({dev['name']}) falha de rede: {e}")

def aditivaflow_sync_loop():
    log_info("[Cloud] Iniciando loop de sincronização AditivaFlow...")
    base_url = "https://iwsqfjngeicyrcdowdbi.supabase.co/functions/v1/device-api"
    
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    
    while KEEP_RUNNING:
        token = load_token()
        if not token:
            time.sleep(10)
            continue
            
        headers = {
            'x-device-token': token,
            'Content-Type': 'application/json',
            'apikey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml3c3Fmam5nZWljeXJjZG93ZGJpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI1NjIzMDksImV4cCI6MjA3ODEzODMwOX0.CM5OO5AoLcVWShMBcpk8oJaYzNU06jHjbH-Oj3X-uAg'
        }
        
        refresh_cloud_metadata(token)
        user_id = CLOUD_METADATA['user_id']
        
        # Sincronizar cada impressora que tenha platform_token (sync_code)
        # Nota: O usuário chamou o campo de 'platform_token' mas a API espera 'sync_code'
        with PRINTERS_LOCK:
            printers_snap = list(PRINTERS)
            
        for p in printers_snap:
            if not KEEP_RUNNING: break
            
            sync_code = p.config.get('platform_token')
            if not sync_code: continue
            
            try:
                status = p.get_status()
                
                # Helpers para garantir arredondamento antes de enviar
                def safe_round(val, decimals=2):
                    try: return round(float(val), decimals)
                    except: return 0
                
                def safe_int(val):
                    try: return int(float(val))
                    except: return 0

                # Normalizar estado conforme pedido
                state_map = {
                    'printing': 'printing', 'running': 'printing',
                    'paused': 'paused', 'error': 'error',
                    'complete': 'complete', 'finish': 'complete', 'success': 'complete',
                    'idle': 'idle', 'ready': 'idle', 'standby': 'standby', 'off': 'off', 'offline': 'off',
                    'cancelled': 'idle', 'stopped': 'idle'
                }
                curr_state = str(status.get('state', 'offline')).lower()
                mapped_state = state_map.get(curr_state, 'idle')

                # Dados de rastreamento para histórico
                if p.config['id'] not in PREVIOUS_PRINTER_STATES:
                    PREVIOUS_PRINTER_STATES[p.config['id']] = {'state': 'offline', 'started_at': None}
                prev_data = PREVIOUS_PRINTER_STATES[p.config['id']]

                prev_state = prev_data['state'].lower()
                is_printing_now = curr_state in ['printing', 'running']
                is_printing_prev = prev_state in ['printing', 'running']
                is_finished_now = curr_state in ['idle', 'complete', 'finish', 'success', 'ready', 'cancelled', 'stopped', 'error', 'failed']
                
                # Capturar hora de início
                if is_printing_now and not prev_data.get('started_at'):
                    elapsed_secs = safe_int(status.get('print_duration', 0) * 60)
                    if elapsed_secs > 0:
                        prev_data['started_at'] = (datetime.now() - timedelta(seconds=elapsed_secs)).isoformat()
                    else:
                        prev_data['started_at'] = datetime.now().isoformat()
                    log_cloud(f"[{p.name}] Impressão iniciada às {prev_data['started_at']}")
                
                if is_printing_prev and is_finished_now:
                    log_cloud(f"Detetado fim de impressão para {p.name}. Enviando histórico...")
                    try:
                        hist_result = "success"
                        if curr_state in ['error', 'failed']:
                            hist_result = "failed"
                        elif curr_state in ['cancelled', 'stopped']:
                            hist_result = "cancelled"

                        history_payload = {
                            "sync_code": sync_code,
                            "filename": status.get('filename', ''),
                            "started_at": prev_data.get('started_at') or datetime.now().isoformat(),
                            "duration_seconds": int(status.get('print_duration', 0)) * 60,
                            "weight_grams": float(status.get('print_weight', 0)),
                            "filament_type": status.get('active_tray_name', ''),
                            "result": hist_result,
                            "avg_temp_nozzle": float(status.get('temp_nozzle', 0)),
                            "avg_temp_bed": float(status.get('temp_bed', 0))
                        }
                        
                        # POST separado para histórico (print-complete)
                        session.post(f"{base_url}/hub/print-complete", headers=headers, json=history_payload, timeout=5)
                        log_cloud(f"Histórico de {p.name} sincronizado com sucesso.")
                        prev_data['started_at'] = None # Reset
                    except Exception as e:
                        log_error(f"Erro ao sincronizar histórico: {e}")

                prev_data['state'] = curr_state

                # Preparar payload conforme especificação
                payload = {
                    "sync_code": sync_code,
                    "state": mapped_state,
                    "temp_nozzle": safe_round(status.get('temp_nozzle', 0)),
                    "temp_bed": safe_round(status.get('temp_bed', 0)),
                    "target_nozzle": safe_round(status.get('target_nozzle', 0)),
                    "target_bed": safe_round(status.get('target_bed', 0)),
                    "chamber_temp": safe_round(status.get('chamber_temp', 0)),
                    "progress": safe_round(status.get('progress', 0), 2),
                    "filename": status.get('filename', ''),
                    "layer": safe_int(status.get('layer', 0)),
                    "total_layers": safe_int(status.get('total_layers', 0)),
                    "total_usage": safe_round(status.get('total_usage', 0.0), 4),
                    "printer_type": p.type,
                    "ip": p.ip,
                    "serial": p.config.get('serial', ''),
                    "wifi_signal": status.get('wifi_signal', 0),
                    "speed_level": status.get('speed_level'),
                    "print_weight": safe_round(status.get('print_weight', 0)),
                    "active_tray_name": status.get('active_tray_name', ''),
                    "active_tray_uuid": status.get('active_tray_uuid', ''),
                    "firmware_version": status.get('firmware_update', {}).get('current', '') if isinstance(status.get('firmware_update'), dict) else status.get('firmware_version', ''),
                    "firmware_version_latest": status.get('firmware_update', {}).get('latest', '') if isinstance(status.get('firmware_update'), dict) else '',
                    "print_error": status.get('print_error'),
                    "led_val": status.get('led_val'),
                    "fan_val": status.get('fan_part') if p.type == 'bambu' else status.get('fan_val'),
                    "fan_aux": status.get('fan_aux', 0),
                    "fan_chamber": status.get('fan_chamber', 0),
                    "ams": status.get('ams', []),
                    "hms": status.get('hms', []),
                    "remaining_time": safe_int(status.get('remaining_time', 0) * 60)
                }

                # Only include dual nozzle fields if they actually exist for this printer (e.g., temp_nozzle_left is not None)
                if status.get('temp_nozzle_left') is not None:
                    payload.update({
                        "temp_nozzle_left": status.get('temp_nozzle_left'),
                        "temp_nozzle_right": status.get('temp_nozzle_right'),
                        "target_nozzle_left": safe_round(status.get('target_nozzle_left', 0)),
                        "target_nozzle_right": safe_round(status.get('target_nozzle_right', 0)),
                        "active_nozzle": status.get('active_nozzle'),
                        "nozzle_diameter_right": status.get('nozzle_diameter_right'),
                        "nozzle_diameter_left": status.get('nozzle_diameter_left'),
                        "nozzle_type_right": status.get('nozzle_type_right'),
                        "nozzle_type_left": status.get('nozzle_type_left'),
                        "nozzle_fila_id_right": status.get('nozzle_fila_id_right'),
                        "nozzle_fila_id_left": status.get('nozzle_fila_id_left'),
                        "nozzle_color_right": status.get('nozzle_color_right'),
                        "nozzle_color_left": status.get('nozzle_color_left'),
                    })

                # Timestamps de controle
                if mapped_state == "complete":
                    payload["completed_at"] = datetime.now().isoformat()
                else:
                    if prev_data.get('started_at'):
                        payload["started_at"] = prev_data.get('started_at')
                    
                    payload["elapsed_time"] = safe_int(status.get('print_duration', 0) * 60)
                    payload["total_estimated_time"] = safe_int(status.get('total_duration', 0) * 60)
                    
                    rem_sec = safe_int(status.get('remaining_time', 0) * 60)
                    if rem_sec > 0:
                        payload["estimated_end_at"] = (datetime.now() + timedelta(seconds=rem_sec)).isoformat()

                # IDs da Nuvem apenas em variavel local para comandos
                machine_id = CLOUD_METADATA['machines'].get(sync_code)

                # 1. Câmera Handling (Base64) - Obtida do buffer em segundo plano (Otimizado)
                frame = None
                img_info = ""
                if hasattr(p, 'last_frame') and p.last_frame:
                    frame = p.last_frame
                    img_info = " [Snap]" if hasattr(p, 'get_snapshot') else " [Stream]"
                
                if frame:
                    payload["camera_frame_base64"] = base64.b64encode(frame).decode('utf-8')
                    img_info += f" {len(frame)/1024:.1f}KB"
                
                thumb_info = ""
                cover = status.get('cover_image')
                if cover:
                    b64_img = ""
                    if p.type == 'bambu':
                        b64_img = cover
                    elif p.type == 'moonraker' and str(cover).startswith('http'):
                        if not hasattr(p, '_last_thumb_url') or p._last_thumb_url != cover:
                            try:
                                t_resp = session.get(cover, timeout=3)
                                if t_resp.status_code == 200:
                                    p._last_thumb_url = cover
                                    p._last_thumb_b64 = base64.b64encode(t_resp.content).decode('utf-8')
                            except: pass
                        if hasattr(p, '_last_thumb_b64'):
                            b64_img = p._last_thumb_b64
                    
                    if b64_img:
                        if not b64_img.startswith("data:"):
                            b64_img = "data:image/png;base64," + b64_img
                        payload["thumbnail_base64"] = b64_img
                        thumb_info = f" [Thumb: {len(b64_img)*0.75/1024:.1f}KB]"

                # Enviar telemetria
                log_cloud(f"Sincronizando {p.name}: {payload['state']} {img_info}{thumb_info}")
                
                # Tentar PATCH (preferencial) ou POST (fallback)
                try:
                    sync_resp = session.patch(f"{base_url}/hub/sync", headers=headers, json=payload, timeout=5)
                    if sync_resp.status_code in [404, 405]:
                        # Se PATCH não existir, tenta POST
                        sync_resp = session.post(f"{base_url}/hub/sync", headers=headers, json=payload, timeout=5)
                except:
                    sync_resp = session.post(f"{base_url}/hub/sync", headers=headers, json=payload, timeout=5)

                if sync_resp.status_code == 200:
                    # Polling de comandos pendentes
                    if machine_id:
                        cmd_resp = session.get(f"{base_url}/hub/commands?machine_id={machine_id}&status=pending", headers=headers, timeout=4)
                        if cmd_resp.status_code == 200:
                            commands = cmd_resp.json().get('data', [])
                            for cmd_obj in commands:
                                cmd_id = cmd_obj.get('id')
                                cmd_name = cmd_obj.get('command')
                                log_cloud(f"Comando recebido para {p.name}: {cmd_name}")
                                
                                # Executar
                                success = False
                                msg = ""
                                try:
                                    if cmd_name in ['pause', 'resume', 'stop']:
                                        p.send_command(cmd_name)
                                        success = True
                                    elif cmd_name == 'led_on':
                                        p.send_command('led', val=100)
                                        success = True
                                    elif cmd_name == 'led_off':
                                        p.send_command('led', val=0)
                                        success = True
                                    else:
                                        msg = f"Comando desconhecido: {cmd_name}"
                                except Exception as e:
                                    msg = str(e)
                                
                                # Confirmar via PATCH (especificação) ou POST (fallback) enviando no corpo
                                conf_payload = {
                                    "success": success,
                                    "status": "completed" if success else "failed",
                                    "confirmed_at": datetime.now().isoformat(),
                                    "confirmation_message": msg or "Comando executado com sucesso"
                                }
                                try:
                                    session.patch(f"{base_url}/hub/command-confirm/{cmd_id}", headers=headers, json=conf_payload, timeout=4)
                                except:
                                    session.post(f"{base_url}/hub/command-confirm/{cmd_id}", headers=headers, json=conf_payload, timeout=4)
                else:
                    log_warn(f"Erro Cloud ({p.name}): Status {sync_resp.status_code} - {sync_resp.text[:120]}")
                
            except Exception as e:
                log_error(f"[Cloud] Erro ao sincronizar {p.config.get('name')}: {e}")
        
        # ── SINCRONIZAÇÃO DE DISPOSITIVOS DE ENERGIA ─────────────────
        _scfg = load_sync_config()
        try:
            energy_config = load_energy_config()
            devs_by_id = {str(d['id']): d for d in energy_config}

            if _scfg.get('sync_on_device_poll'):
                # Modo "na frequência dos dispositivos" – drena a fila
                synced_ids = set()
                while True:
                    try:
                        dev_id = ENERGY_SYNC_QUEUE.get_nowait()
                        str_id = str(dev_id)
                        if str_id in synced_ids: continue
                        synced_ids.add(str_id)
                        dev = devs_by_id.get(str_id)
                        if dev:
                            _sync_one_energy_device(dev, session, headers, base_url)
                    except _queue_mod.Empty:
                        break
            else:
                # Modo intervalo fixo – sincroniza todos agora
                for dev in energy_config:
                    if not KEEP_RUNNING: break
                    sync_code = dev.get('code')
                    if not sync_code: continue
                    try:
                        _sync_one_energy_device(dev, session, headers, base_url)
                    except Exception as e:
                        log_error(f"[Cloud] Erro ao sincronizar dispositivo energia {dev.get('name')}: {e}")
        except Exception as e:
            log_error(f"[Cloud] Erro ao carregar config de energia para sync: {e}")
        
        time.sleep(5) # Intervalo entre ciclos de sync

def save_usage_periodically():
    while KEEP_RUNNING:
        time.sleep(300) # Save every 5 minutes
        config = load_config()
        if not config: continue
        changed = False
        with PRINTERS_LOCK:
            printers_snap = list(PRINTERS)
        for pr in printers_snap:
            current_usage = round(pr.status.get('total_usage', 0), 4)
            for p_cfg in config:
                if p_cfg['id'] == pr.config['id']:
                    if abs(p_cfg.get('total_usage', 0) - current_usage) > 0.0001:
                        p_cfg['total_usage'] = current_usage
                        changed = True
        if changed:
            save_config(config)
            log_info(f"[System] Horas de uso persistidas no config.json")

def start_background_tasks():
    global KEEP_RUNNING
    KEEP_RUNNING = True
    log_info("[System] Iniciando serviços de background...")
    update_printers_once()
    threading.Thread(target=save_usage_periodically, daemon=True, name="UsageSaver").start()
    threading.Thread(target=polling_loop, daemon=True, name="PollingLoop").start()
    threading.Thread(target=aditivaflow_sync_loop, daemon=True, name="CloudSync").start()
    threading.Thread(target=energy_polling_loop, daemon=True, name="EnergyPolling").start()

if __name__ == '__main__':
    import socket
    import sys
    
    # Prevenção Absoluta Anti-Zumbi (Single Instance)
    try:
        instance_lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        instance_lock.bind(('127.0.0.1', 54321))
    except socket.error:
        log_error("\n!!! ALERTA DE SEGURANÇA !!!")
        log_error("Uma instância do AditivaFlow Hub JÁ ESTÁ RODANDO em segundo plano!")
        log_error("Fechar imediatamente. Múltiplas instâncias geram conflitos no servidor.")
        sys.exit(1)

    log_info(f"Hub Server Iniciado!")
    start_background_tasks()
    
    try:
        from waitress import serve
        log_info("[System] Usando servidor de produção Waitress em 0.0.0.0:5000 ...")
        serve(app, host='0.0.0.0', port=5000, threads=24)
    except ImportError:
        log_warn("[System] Waitress não instalado. Rodando em Flask Development Server.")
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
