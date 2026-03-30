#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# AditivaFlow Hub - Instalador Linux
# Uso: curl -sSL https://raw.githubusercontent.com/gabrielbolzani/3d_printer_connection_hub/main/install.sh | bash
# ─────────────────────────────────────────────────────────────────────────────

# Cores ANSI
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
DIM='\033[2m'
RESET='\033[0m'
BOLD='\033[1m'

clear

# ─────────────────────────────────────────────────────────────────────────────
# BANNER ASCII
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}"
cat << 'EOF'
    ___       ___ __  _              ________
   /   | ____/ (_) /_(_)   ______ _/ ____/ /___ _      __
  / /| |/ __  / / __/ / | / / __ `/ /_  / / __ \ | /| / /
 / ___ / /_/ / / /_/ /| |/ / /_/ / __/ / / /_/ / |/ |/ /
/_/  |_\__,_/_/\__/_/ |___/\__,_/_/   /_/\____/|__/|__/

EOF
echo -e "${RESET}"
echo -e "${BLUE}${BOLD}"
cat << 'EOF'
  ██╗  ██╗██╗   ██╗██████╗
  ██║  ██║██║   ██║██╔══██╗
  ███████║██║   ██║██████╔╝
  ██╔══██║██║   ██║██╔══██╗
  ██║  ██║╚██████╔╝██████╔╝
  ╚═╝  ╚═╝ ╚═════╝ ╚═════╝

EOF
echo -e "${RESET}"
echo -e "${DIM}  ┌─────────────────────────────────────────────────────┐${RESET}"
echo -e "${DIM}  │  Gerenciador de Impressoras 3D · AditivaFlow Hub    │${RESET}"
echo -e "${DIM}  └─────────────────────────────────────────────────────┘${RESET}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
REPO="gabrielbolzani/3d_printer_connection_hub"
INSTALL_DIR="/opt/aditivaflow-hub"
SERVICE_NAME="aditivaflow-hub"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
VENV_DIR="${INSTALL_DIR}/venv"
PORT=5000

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
info()    { echo -e "  ${CYAN}▶${RESET} $*"; }
success() { echo -e "  ${GREEN}✔${RESET} $*"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET} $*"; }
error()   { echo -e "  ${RED}✖${RESET} $*" >&2; }
step()    { echo ""; echo -e "  ${BOLD}${WHITE}$*${RESET}"; echo -e "  ${DIM}$(printf '─%.0s' {1..50})${RESET}"; }

require_root() {
    if [[ $EUID -ne 0 ]]; then
        error "Este instalador precisa ser executado como root."
        echo -e "  ${DIM}Tente: sudo bash <(curl -sSL https://raw.githubusercontent.com/${REPO}/main/install.sh)${RESET}"
        exit 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# PRE-CHECKS
# ─────────────────────────────────────────────────────────────────────────────
require_root

step "1/6 · Verificando dependências do sistema"

# Python 3.9+
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 9 ]]; then
        success "Python $PY_VER encontrado"
    else
        warn "Python $PY_VER encontrado, mas recomendamos 3.9+. Tentando instalar..."
        apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv
    fi
else
    info "Python 3 não encontrado. Instalando..."
    apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv
    success "Python instalado"
fi

# pip & venv
if ! python3 -m venv --help &>/dev/null; then
    info "Instalando python3-venv..."
    apt-get install -y -qq python3-venv
fi

# curl / wget
if ! command -v curl &>/dev/null && ! command -v wget &>/dev/null; then
    info "Instalando curl..."
    apt-get install -y -qq curl
fi

# ffmpeg — necessário para câmera Bambu X1C
if command -v ffmpeg &>/dev/null; then
    success "FFmpeg encontrado"
else
    info "FFmpeg não encontrado. Instalando (necessário para câmera X1C)..."
    apt-get install -y -qq ffmpeg && success "FFmpeg instalado" || warn "FFmpeg não pôde ser instalado automaticamente. A câmera X1C pode não funcionar."
fi

# jq — para parsear JSON da API do GitHub
if ! command -v jq &>/dev/null; then
    apt-get install -y -qq jq 2>/dev/null || true
fi

# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD
# ─────────────────────────────────────────────────────────────────────────────
step "2/6 · Baixando a versão mais recente do AditivaFlow Hub"

API_URL="https://api.github.com/repos/${REPO}/releases/latest"
if command -v jq &>/dev/null; then
    LATEST_TAG=$(curl -sSL "$API_URL" | jq -r '.tag_name')
    TARBALL_URL=$(curl -sSL "$API_URL" | jq -r '.assets[] | select(.name | endswith(".tar.gz")) | .browser_download_url' | head -1)
fi

# Fallback se jq não estiver disponível
if [[ -z "${LATEST_TAG:-}" || "$LATEST_TAG" == "null" ]]; then
    LATEST_TAG=$(curl -sSL -o /dev/null -w '%{url_effective}' "https://github.com/${REPO}/releases/latest" | grep -oP 'v[\d.]+$' || echo "main")
    TARBALL_URL=""
fi

info "Versão: ${BOLD}${LATEST_TAG}${RESET}"

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ -n "${TARBALL_URL:-}" && "$TARBALL_URL" != "null" ]]; then
    info "Baixando release empacotado..."
    curl -sSL "$TARBALL_URL" -o "$TMP_DIR/hub.tar.gz"
    tar -xzf "$TMP_DIR/hub.tar.gz" -C "$TMP_DIR"
    # Encontrar a pasta extraída
    SRC_DIR=$(find "$TMP_DIR" -maxdepth 2 -name "app.py" -exec dirname {} \; | head -1)
else
    # Fallback: baixar source code direto do branch main
    info "Baixando código-fonte do branch main..."
    curl -sSL "https://github.com/${REPO}/archive/refs/heads/main.tar.gz" -o "$TMP_DIR/hub.tar.gz"
    tar -xzf "$TMP_DIR/hub.tar.gz" -C "$TMP_DIR"
    SRC_DIR=$(find "$TMP_DIR" -maxdepth 2 -name "app.py" -exec dirname {} \; | head -1)
fi

if [[ -z "$SRC_DIR" ]]; then
    error "Não foi possível encontrar os arquivos do AditivaFlow Hub no pacote baixado."
    exit 1
fi
success "Download concluído"

# ─────────────────────────────────────────────────────────────────────────────
# INSTALAÇÃO
# ─────────────────────────────────────────────────────────────────────────────
step "3/6 · Instalando arquivos em ${INSTALL_DIR}"

# Preservar config.json se já existir
if [[ -f "${INSTALL_DIR}/config.json" ]]; then
    info "config.json existente encontrado — preservando configurações..."
    cp "${INSTALL_DIR}/config.json" "$TMP_DIR/config.json.bak"
fi
if [[ -f "${INSTALL_DIR}/auth_token.json" ]]; then
    cp "${INSTALL_DIR}/auth_token.json" "$TMP_DIR/auth_token.json.bak"
fi

# Copiar arquivos
mkdir -p "$INSTALL_DIR"
cp -r "$SRC_DIR"/. "$INSTALL_DIR/"

# Restaurar config
if [[ -f "$TMP_DIR/config.json.bak" ]]; then
    cp "$TMP_DIR/config.json.bak" "${INSTALL_DIR}/config.json"
    success "Configurações preservadas"
fi
if [[ -f "$TMP_DIR/auth_token.json.bak" ]]; then
    cp "$TMP_DIR/auth_token.json.bak" "${INSTALL_DIR}/auth_token.json"
fi

success "Arquivos instalados em ${INSTALL_DIR}"

# ─────────────────────────────────────────────────────────────────────────────
# AMBIENTE VIRTUAL PYTHON
# ─────────────────────────────────────────────────────────────────────────────
step "4/6 · Criando ambiente virtual Python e instalando dependências"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"
success "Dependências Python instaladas"

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEMD
# ─────────────────────────────────────────────────────────────────────────────
step "5/6 · Configurando serviço systemd (início automático)"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=AditivaFlow Hub - Gerenciador de Impressoras 3D
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/app.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" &>/dev/null
systemctl restart "$SERVICE_NAME"

# Aguarda inicialização
sleep 3
if systemctl is-active --quiet "$SERVICE_NAME"; then
    success "Serviço '${SERVICE_NAME}' ativo e rodando"
else
    warn "Serviço iniciou mas não está ativo. Verifique com: journalctl -u ${SERVICE_NAME} -n 30"
fi

# ─────────────────────────────────────────────────────────────────────────────
# FINALIZAÇÃO
# ─────────────────────────────────────────────────────────────────────────────
step "6/6 · Instalação concluída!"

# Detectar IP local
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo ""
echo -e "  ${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗${RESET}"
echo -e "  ${GREEN}${BOLD}║      ✅  AditivaFlow Hub instalado com sucesso!      ║${RESET}"
echo -e "  ${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${WHITE}Acesse o painel em:${RESET}"
echo -e "  ${CYAN}${BOLD}  ➜  http://${LOCAL_IP}:${PORT}${RESET}"
echo -e "  ${DIM}  ➜  http://localhost:${PORT}${RESET}"
echo ""
echo -e "  ${WHITE}Comandos úteis:${RESET}"
echo -e "  ${DIM}  • Ver logs em tempo real:  ${RESET}${YELLOW}journalctl -fu ${SERVICE_NAME}${RESET}"
echo -e "  ${DIM}  • Parar o serviço:         ${RESET}${YELLOW}systemctl stop ${SERVICE_NAME}${RESET}"
echo -e "  ${DIM}  • Reiniciar:               ${RESET}${YELLOW}systemctl restart ${SERVICE_NAME}${RESET}"
echo -e "  ${DIM}  • Atualizar:               ${RESET}${YELLOW}curl -sSL https://raw.githubusercontent.com/${REPO}/main/install.sh | bash${RESET}"
echo ""
echo -e "  ${DIM}Arquivos instalados em: ${INSTALL_DIR}${RESET}"
echo -e "  ${DIM}Versão: ${LATEST_TAG}${RESET}"
echo ""
