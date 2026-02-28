from flask import Flask, render_template, request, jsonify, abort
import threading
import time
import json
import os
import psutil
import signal
import sys
import requests
import base64
from printer_drivers import create_printer_from_config
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

CONFIG_FILE = 'config.json'
PRINTERS = []
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

# Global state for rate calculations
LAST_PROC_IO = None
LAST_PROC_TIME = None
APP_START_TIME = time.time()
executor = ThreadPoolExecutor(max_workers=20)
KEEP_RUNNING = True
PREVIOUS_PRINTER_STATES = {} # Para detecção de conclusão de impressão
CLOUD_METADATA = {'user_id': None, 'machines': {}, 'last_refresh': 0}

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

    config_map = {p['id']: p for p in current_config}
    
    # Remove deleted printers
    for p in PRINTERS:
        pid = p.config['id']
        if pid not in config_map:
            try: p.stop()
            except: pass
            if pid in STATUS_CACHE:
                del STATUS_CACHE[pid]
    PRINTERS[:] = [p for p in PRINTERS if p.config['id'] in config_map]

    # Update existing or add new
    current_ids = [p.config['id'] for p in PRINTERS]
    
    for p_conf in current_config:
        if p_conf['id'] not in current_ids:
            new_p = create_printer_from_config(p_conf)
            if new_p:
                PRINTERS.append(new_p)
        else:
            for p in PRINTERS:
                if p.config['id'] == p_conf['id']:
                    p.config = p_conf
                    p.ip = p_conf.get('ip')
                    break
    
    # Sort PRINTERS list to match config order
    id_to_pos = {p['id']: i for i, p in enumerate(current_config)}
    PRINTERS.sort(key=lambda p: id_to_pos.get(p.config['id'], 999))

def update_p(p):
    try:
        if not p.config.get('enabled', True):
            s = p.get_status()
            s['state'] = 'off'
            STATUS_CACHE[p.config['id']] = s
            return
        p.update()
        STATUS_CACHE[p.config['id']] = p.get_status()
    except Exception as e:
        log_error(f"Update failed for {p.config.get('name')}: {e}")

def polling_loop():
    while KEEP_RUNNING:
        try:
            update_printers_once()
            if not KEEP_RUNNING: break
            for p in PRINTERS:
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
    for p in PRINTERS:
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

@app.route('/console')
def console_page():
    return render_template('console.html')

@app.route('/auth')
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
    # Mask token for security
    masked = token # In production we might want to mask it: '*' * (len(token)-4) + token[-4:] if len(token) > 4 else token
    return jsonify({'token': masked})

@app.route('/api/printers', methods=['GET'])
def get_printers():
    # Return printers in the order of the PRINTERS list (which matches config)
    ordered_status = []
    for p in PRINTERS:
        pid = p.config['id']
        if pid in STATUS_CACHE:
            ordered_status.append(STATUS_CACHE[pid])
        else:
            # Fallback if not updated yet
            ordered_status.append(p.get_status())
    return jsonify(ordered_status)

@app.route('/api/camera/<printer_id>', methods=['GET'])
def get_camera_frame(printer_id):
    printer = next((p for p in PRINTERS if p.config['id'] == printer_id), None)
    if printer:
        # Check for cached frame (Bambu)
        if hasattr(printer, 'last_frame') and printer.last_frame:
            from flask import Response
            return Response(printer.last_frame, mimetype='image/jpeg')
        
        # Check for on-demand snapshot (Moonraker)
        if hasattr(printer, 'get_snapshot'):
            frame = printer.get_snapshot()
            if frame:
                from flask import Response
                return Response(frame, mimetype='image/jpeg')
                
    return jsonify({'error': 'No frame available'}), 404

@app.route('/api/raw_status/<printer_id>', methods=['GET'])
def raw_status(printer_id):
    printer = next((p for p in PRINTERS if p.config['id'] == printer_id), None)
    if printer:
        return jsonify({
            'config': printer.config,
            'status': printer.status,
            'last_update': printer.last_update
        })
    return jsonify({'error': 'Printer not found'}), 404

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
        'enabled': True
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
            if p['type'] == 'elegoo':
                p['port'] = 3000
            else:
                p['port'] = int(data.get('port', p.get('port', 80)))
            break
    save_config(config)
    global PRINTERS
    # Parar e remover a instância antiga para forçar a criação de uma nova
    for pr in PRINTERS:
        if str(pr.config['id']) == str(p_id):
            try: pr.stop()
            except: pass
            
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
    config = [p for p in config if p['id'] != p_id]
    save_config(config)
    
    global PRINTERS
    for pr in PRINTERS:
        if str(pr.config['id']) == str(p_id):
            try: pr.stop()
            except: pass
    PRINTERS[:] = [pr for pr in PRINTERS if str(pr.config['id']) != str(p_id)]
    
    update_printers_once()
    return jsonify({"success": True})

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

def aditivaflow_sync_loop():
    log_info("[Cloud] Iniciando loop de sincronização AditivaFlow...")
    base_url = "https://iwsqfjngeicyrcdowdbi.supabase.co/functions/v1/device-api"
    
    while KEEP_RUNNING:
        token = load_token()
        if not token:
            time.sleep(10)
            continue
            
        headers = {
            'x-device-token': token,
            'Content-Type': 'application/json'
        }
        
        refresh_cloud_metadata(token)
        user_id = CLOUD_METADATA['user_id']
        
        # Sincronizar cada impressora que tenha platform_token (sync_code)
        # Nota: O usuário chamou o campo de 'platform_token' mas a API espera 'sync_code'
        for p in PRINTERS:
            if not KEEP_RUNNING: break
            
            sync_code = p.config.get('platform_token')
            if not sync_code: continue
            
            try:
                status = p.get_status()
                
                # Preparar payload conforme especificação
                payload = {
                    "sync_code": sync_code,
                    "state": status.get('state', 'offline'),
                    "temp_nozzle": status.get('temp_nozzle', 0),
                    "temp_bed": status.get('temp_bed', 0),
                    "target_nozzle": status.get('target_nozzle', 0),
                    "target_bed": status.get('target_bed', 0),
                    "progress": status.get('progress', 0),
                    "filename": status.get('filename', ''),
                    "remaining_time": status.get('remaining_time', 0) * 60,
                    "remaining_time_seconds": status.get('remaining_time', 0) * 60,
                    "total_estimated_seconds": int(status.get('total_duration', 0)) * 60,
                    "layer": status.get('layer', 0),
                    "total_layers": status.get('total_layers', 0),
                    "total_usage": status.get('total_usage', 0.0),
                    "printer_type": p.type,
                    "ip": p.ip,
                    "serial": p.config.get('serial', ''),
                    "speed_level": status.get('speed_level'),
                    "print_weight": status.get('print_weight', 0),
                    "active_tray_name": status.get('active_tray_name', ''),
                    "firmware_version": status.get('firmware_update', {}).get('current', ''),
                    "print_error": status.get('print_error'),
                    "led_val": status.get('led_val'),
                    "fan_val": status.get('fan_val'),
                    "print_duration": int(status.get('print_duration', 0)) * 60,
                    "total_duration": int(status.get('total_duration', 0)) * 60
                }
                
                # Normalizar estado conforme pedido
                state_map = {
                    'printing': 'printing', 'running': 'printing',
                    'paused': 'paused', 'error': 'error',
                    'complete': 'complete', 'finish': 'complete', 'success': 'complete',
                    'idle': 'idle', 'ready': 'idle', 'standby': 'standby', 'off': 'off', 'offline': 'off'
                }
                curr_state = str(status.get('state', 'offline')).lower()
                payload['state'] = state_map.get(curr_state, 'idle')

                # IDs da Nuvem
                machine_id = CLOUD_METADATA['machines'].get(sync_code)
                payload['user_id'] = user_id
                payload['machine_id'] = machine_id

                # Dados de rastreamento para histórico
                if p.config['id'] not in PREVIOUS_PRINTER_STATES:
                    PREVIOUS_PRINTER_STATES[p.config['id']] = {'state': 'offline', 'started_at': None}
                prev_data = PREVIOUS_PRINTER_STATES[p.config['id']]

                # Detecção de Início e Conclusão de Impressão
                prev_state = prev_data['state'].lower()
                is_printing_now = curr_state in ['printing', 'running']
                is_printing_prev = prev_state in ['printing', 'running']
                is_finished_now = curr_state in ['idle', 'complete', 'finish', 'success', 'ready']
                
                # Capturar hora de início
                if is_printing_now and not is_printing_prev:
                    prev_data['started_at'] = datetime.now().isoformat()
                    log_cloud(f"[{p.name}] Impressão iniciada às {prev_data['started_at']}")
                
                if is_printing_prev and is_finished_now:
                    log_cloud(f"Detetado fim de impressão para {p.name}. Enviando histórico...")
                    try:
                        history_payload = {
                            "action": "sync_print_history",
                            "machine_id": machine_id,
                            "prints": [
                                {
                                    "filename": status.get('filename'),
                                    "status": "completed",
                                    "started_at": prev_data.get('started_at'),
                                    "completed_at": datetime.now().isoformat(),
                                    "print_duration_seconds": int(status.get('print_duration', 0)) * 60,
                                    "estimated_total_seconds": int(status.get('total_duration', 0)) * 60,
                                    "weight_grams": status.get('print_weight', 0),
                                    "filament_weight_grams": status.get('print_weight', 0), # Bambu weight já é o consumo
                                    "filament_used": status.get('active_tray_name', ''),
                                    "layer_count": status.get('total_layers', 0),
                                    "bed_temp": status.get('temp_bed', 0),
                                    "nozzle_temp": status.get('temp_nozzle', 0),
                                    "thumbnail_url": f"https://iwsqfjngeicyrcdowdbi.supabase.co/storage/v1/object/public/machine-media/camera/{user_id}/{machine_id}/latest.jpg" if user_id and machine_id else None
                                }
                            ]
                        }
                        # Enviar para o endpoint de API geral com a action solicitada
                        requests.post(base_url, headers=headers, json=history_payload, timeout=10)
                        log_cloud(f"Histórico de {p.name} sincronizado com sucesso.")
                        prev_data['started_at'] = None # Reset
                    except Exception as e:
                        log_error(f"Erro ao sincronizar histórico: {e}")

                prev_data['state'] = curr_state

                # 1. Câmera Handling (Bucket Upload)
                frame = None
                img_info = ""
                if hasattr(p, 'last_frame') and p.last_frame:
                    frame = p.last_frame
                    img_info = " [Stream]"
                elif hasattr(p, 'get_snapshot'):
                    frame = p.get_snapshot()
                    img_info = " [Snapshot]"
                
                if frame and user_id and machine_id:
                    try:
                        storage_url = "https://iwsqfjngeicyrcdowdbi.supabase.co/storage/v1/object/machine-media"
                        cam_path = f"camera/{user_id}/{machine_id}/latest.jpg"
                        storage_headers = {
                            'Authorization': f'Bearer {token}', 
                            'x-device-token': token,
                            'Content-Type': 'image/jpeg'
                        }
                        requests.put(f"{storage_url}/{cam_path}", headers=storage_headers, data=frame, timeout=8)
                        img_info += f" {len(frame)/1024:.1f}KB (Bucket)"
                    except Exception as e:
                        log_error(f"Erro upload câmera {p.name}: {e}")
                
                thumb_info = ""
                cover = status.get('cover_image')
                if cover:
                    b64_img = ""
                    if p.type == 'bambu':
                        b64_img = cover
                    elif p.type == 'moonraker' and str(cover).startswith('http'):
                        if not hasattr(p, '_last_thumb_url') or p._last_thumb_url != cover:
                            try:
                                t_resp = requests.get(cover, timeout=5)
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
                        payload["cover_image_base64"] = b64_img
                        thumb_info = f" [Thumb: {len(b64_img)*0.75/1024:.1f}KB]"

                # Enviar telemetria
                log_cloud(f"Sincronizando {p.name}: {payload['state']} {img_info}{thumb_info}")
                
                # Tentar PATCH (preferencial) ou POST (fallback)
                try:
                    sync_resp = requests.patch(f"{base_url}/hub/sync", headers=headers, json=payload, timeout=12)
                    if sync_resp.status_code in [404, 405]:
                        # Se PATCH não existir, tenta POST
                        sync_resp = requests.post(f"{base_url}/hub/sync", headers=headers, json=payload, timeout=12)
                except:
                    sync_resp = requests.post(f"{base_url}/hub/sync", headers=headers, json=payload, timeout=12)

                if sync_resp.status_code == 200:
                    # Polling de comandos pendentes
                    if machine_id:
                        cmd_resp = requests.get(f"{base_url}/hub/commands?machine_id={machine_id}&status=pending", headers=headers, timeout=5)
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
                                    requests.patch(f"{base_url}/hub/command-confirm/{cmd_id}", headers=headers, json=conf_payload, timeout=5)
                                except:
                                    requests.post(f"{base_url}/hub/command-confirm/{cmd_id}", headers=headers, json=conf_payload, timeout=5)
                else:
                    log_warn(f"Erro Cloud ({p.name}): Status {sync_resp.status_code} - {sync_resp.text[:120]}")
                
            except Exception as e:
                log_error(f"[Cloud] Erro ao sincronizar {p.config.get('name')}: {e}")
        
        time.sleep(5) # Intervalo entre ciclos de sync

if __name__ == '__main__':
    # Flask reloader will run this twice. We only want to start threads in the child process.
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        log_info("[System] Iniciando serviços de background...")
        update_printers_once()
        
        def save_usage_periodically():
            while True:
                time.sleep(300) # Save every 5 minutes
                config = load_config()
                changed = False
                for pr in PRINTERS:
                    current_usage = round(pr.status.get('total_usage', 0), 4)
                    for p_cfg in config:
                        if p_cfg['id'] == pr.config['id']:
                            if abs(p_cfg.get('total_usage', 0) - current_usage) > 0.0001:
                                p_cfg['total_usage'] = current_usage
                                changed = True
                if changed:
                    save_config(config)
                    log_info(f"[System] Horas de uso persistidas no config.json")

        threading.Thread(target=save_usage_periodically, daemon=True, name="UsageSaver").start()
        threading.Thread(target=polling_loop, daemon=True, name="PollingLoop").start()
        threading.Thread(target=aditivaflow_sync_loop, daemon=True, name="CloudSync").start()
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=True, use_debugger=False)
