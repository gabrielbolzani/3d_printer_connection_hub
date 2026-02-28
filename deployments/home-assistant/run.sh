#!/usr/bin/with-contenv bashio

echo "------------------------------------------------"
echo "   Iniciando AditivaFlow Hub para Home Assistant"
echo "------------------------------------------------"

# HA Add-ons often store persistent data in /data
CONFIG_PATH="/data/config.json"
AUTH_PATH="/data/auth_token.json"

# Move config files if they don't exist in /data to ensure persistence
if [ ! -f "$CONFIG_PATH" ]; then
    if [ -f "/app/config.json" ]; then
        cp /app/config.json "$CONFIG_PATH"
    else
        echo "[]" > "$CONFIG_PATH"
    fi
fi

# Symbolic link to allow app.py to find them in its CWD
ln -sf "$CONFIG_PATH" /app/config.json
if [ -f "$AUTH_PATH" ]; then
    ln -sf "$AUTH_PATH" /app/auth_token.json
fi

# Run the application
cd /app
export WERKZEUG_RUN_MAIN=true # Ensure background threads start
python3 app.py
