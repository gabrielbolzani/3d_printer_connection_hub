from flask import Flask, render_template, request, jsonify
import threading
import time
import json
import os
import psutil
from printer_drivers import create_printer_from_config

app = Flask(__name__)

CONFIG_FILE = 'config.json'
PRINTERS = []
STATUS_CACHE = {}
AUTH_FILE = 'auth_token.json'

# Global state for rate calculations
LAST_PROC_IO = None
LAST_PROC_TIME = None
APP_START_TIME = time.time()

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_config(printers_config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(printers_config, f, indent=4)

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


def polling_loop():
    while True:
        global PRINTERS
        current_config = load_config()
        
        # Check if config changed (naive check: count)
        # Ideally we should see if new printers added/removed
        # For simplicity, if count/metadata differs, reload all objects.
        
        # Or simply iterate over current objects and update them.
        # But if user adds a printer via UI, we need to instantiate it.
        
        # Better approach for this MVP: 
        # UI updates config.json.
        # Polling loop sees config, manages pool of printer objects.
        
        # Create map of current config:
        config_map = {p['id']: p for p in current_config}
        
        # Remove deleted printers
        PRINTERS[:] = [p for p in PRINTERS if p.config['id'] in config_map]

        # Update existing or add new
        current_ids = [p.config['id'] for p in PRINTERS]
        
        for p_conf in current_config:
            if p_conf['id'] not in current_ids:
                # New printer
                new_p = create_printer_from_config(p_conf)
                if new_p:
                    PRINTERS.append(new_p)
            else:
                # Update config in case IP changed (requires re-init usually)
                pass

        # Poll Status
        for p in PRINTERS:
            try:
                p.update()
                STATUS_CACHE[p.config['id']] = p.get_status()
            except Exception as e:
                print(f"Update failed for {p.config.get('name')}: {e}")

        time.sleep(5)

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
    return jsonify(list(STATUS_CACHE.values()))

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
        'port': int(data.get('port', 80)), # Default HTTP port
        'serial': data.get('serial', ''),
        'access_code': data.get('access_code', '')
    }
    
    if new_printer['type'] == 'elegoo':
        new_printer['port'] = 3000
    
    config.append(new_printer)
    save_config(config)
    
    # Trigger immediate reload in polling loop or wait
    return jsonify({"success": True, "id": new_id})

@app.route('/api/delete_printer', methods=['POST'])
def delete_printer():
    data = request.json
    p_id = data.get('id')
    config = load_config()
    config = [p for p in config if p['id'] != p_id]
    save_config(config)
    return jsonify({"success": True})

@app.route('/api/control', methods=['POST'])
def control_printer():
    data = request.json
    p_id = data.get('id')
    command = data.get('command')
    
    printer = next((p for p in PRINTERS if p.config['id'] == p_id), None)
    if printer:
        printer.send_command(command)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Printer not found"}), 404

if __name__ == '__main__':
    # Start polling thread
    t = threading.Thread(target=polling_loop, daemon=True)
    t.start()
    
    # Run server
    app.run(host='0.0.0.0', port=5000, debug=True)
