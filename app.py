from flask import Flask, render_template, request, jsonify
import threading
import time
import json
import os
import psutil
import signal
import sys
from printer_drivers import create_printer_from_config
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

CONFIG_FILE = 'config.json'
PRINTERS = []
STATUS_CACHE = {}
APP_START_TIME = time.time()
from logger_config import log_info, log_error, log_warn
AUTH_FILE = 'auth_token.json'

# Global state for rate calculations
LAST_PROC_IO = None
LAST_PROC_TIME = None
APP_START_TIME = time.time()
executor = ThreadPoolExecutor(max_workers=20)
KEEP_RUNNING = True

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

@app.route('/auth')
def auth():
    return render_template('auth.html')

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
            p['camera_refresh'] = data.get('camera_refresh', p.get('camera_refresh', False))
            p['refresh_interval'] = int(data.get('refresh_interval', p.get('refresh_interval', 5000)))
            p['access_code'] = data.get('access_code', p.get('access_code', ''))
            p['platform_token'] = data.get('platform_token', p.get('platform_token', ''))
            if p['type'] == 'elegoo':
                p['port'] = 3000
            else:
                p['port'] = int(data.get('port', p.get('port', 80)))
            break
    save_config(config)
    global PRINTERS
    PRINTERS[:] = [pr for pr in PRINTERS if pr.config['id'] != p_id]
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

if __name__ == '__main__':
    # Flask reloader will run this twice. We only want to start threads in the child process.
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        log_info("[System] Iniciando serviços de background...")
        update_printers_once()
        t = threading.Thread(target=polling_loop, daemon=True, name="PollingLoop")
        t.start()
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=True)
