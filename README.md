# 🚀 AditivaFlow Hub

> **Gerenciador centralizado de impressoras 3D** — conecta sua fazenda local à nuvem AditivaFlow, seja qual for a marca.

O **AditivaFlow Hub** atua como gateway inteligente na sua rede local: instale em qualquer máquina (Raspberry Pi, PC Windows, servidor Linux), e ele conecta, traduz e envia telemetria, vídeo de câmera e controle de **todas as suas impressoras** diretamente para a plataforma [AditivaFlow](https://aditivaflow.com.br).

![GitHub release (latest)](https://img.shields.io/github/v/release/gabrielbolzani/3d_printer_connection_hub?style=flat-square&color=2ea043)
![GitHub license](https://img.shields.io/github/license/gabrielbolzani/3d_printer_connection_hub?style=flat-square)

---

## 🖨️ Impressoras Suportadas

| Marca / Sistema | Modelos | Recursos |
|---|---|---|
| **Bambu Lab** | X1C, X1E, P1S, P1P, A1, A1 Mini | MQTT LAN, câmera RTSP, AMS, HMS, telemetria completa |
| **Klipper / Moonraker** | Voron, RatRig, Creality K1, Ender adaptada e qualquer Klipper | Câmera, controle de fans/LED, G-Code, Pause/Resume/Cancel |
| **Elegoo (Resina)** | Saturn 3 Ultra, Mars series | Status via rede, andamento de impressão |

---

## 📦 Instalação

Escolha o método ideal para o seu ambiente. Todos os executáveis prontos estão na aba **[Releases](https://github.com/gabrielbolzani/3d_printer_connection_hub/releases)**.

---

### 🪟 Windows — Instalador ou Executável Portátil

**Melhor para:** Usuários comuns, PCs desktop, máquinas sem terminal.

#### Opção A — Instalador automático *(Recomendado para Windows)*

1. Baixe o arquivo `AditivaFlowHub-Setup.exe` na última **[Release](https://github.com/gabrielbolzani/3d_printer_connection_hub/releases/latest)**
2. Execute e siga a tela de instalação *"Avançar → Instalar"*
3. O Hub será iniciado automaticamente em background e junto ao Windows

> **⚠️ Alerta do SmartScreen:** Como o executável não possui assinatura de código corporativa, o Windows pode exibir um aviso em tela azul. Clique em **"Mais informações"** → **"Executar assim mesmo"**. Os arquivos das Releases são 100% seguros e verificados pelo GitHub Actions.

#### Opção B — Executável portátil *(sem instalação)*

1. Baixe o arquivo `AditivaFlowHub-Windows.exe` na última **[Release](https://github.com/gabrielbolzani/3d_printer_connection_hub/releases/latest)**
2. Coloque em qualquer pasta e execute quando quiser
3. Ideal para testes, homologações ou sem intenção de deixar em background

---

### 🐧 Linux — Três opções de instalação

**Melhor para:** Raspberry Pi, servidores headless, Proxmox, VPS.

---

#### ⭐ Opção 1 — Instalador via `curl` *(Recomendado para Linux)*

**Uma linha no terminal faz tudo automaticamente:** instala dependências do sistema, cria virtualenv Python, configura como serviço systemd e inicia o Hub.

```bash
sudo bash <(curl -sSL https://raw.githubusercontent.com/gabrielbolzani/3d_printer_connection_hub/main/install.sh)
```

O que o instalador faz:
- ✅ Verifica e instala Python 3, pip, venv e FFmpeg (necessário para câmera X1C)
- ✅ Baixa automaticamente a versão mais recente do GitHub Releases
- ✅ Preserva seu `config.json` e `auth_token.json` em atualizações
- ✅ Cria e ativa um serviço systemd (inicia com o sistema)
- ✅ Exibe o IP local ao final para você acessar imediatamente

Após a instalação, gerencie o serviço com:

```bash
# Ver logs em tempo real
journalctl -fu aditivaflow-hub

# Parar
systemctl stop aditivaflow-hub

# Reiniciar
systemctl restart aditivaflow-hub

# Atualizar para a versão mais recente (basta rodar o instalador de novo)
sudo bash <(curl -sSL https://raw.githubusercontent.com/gabrielbolzani/3d_printer_connection_hub/main/install.sh)
```

---

#### Opção 2 — Docker / Docker Compose *(Melhor isolamento)*

**Melhor para:** quem quer isolamento total do ambiente Python sem afetar o sistema operacional base.

```bash
git clone https://github.com/gabrielbolzani/3d_printer_connection_hub.git
cd 3d_printer_connection_hub
docker-compose up -d --build
```

O Hub estará acessível em `http://localhost:5000`. O argumento `-d` libera o terminal e deixa o container rodando em background.

Para atualizar:
```bash
git pull
docker-compose down && docker-compose up -d --build
```

---

#### Opção 3 — Pacote `.tar.gz` manual

**Melhor para:** usuários avançados que querem controle total de onde e como o Hub está installado.

1. Baixe o arquivo `aditivaflow-hub.tar.gz` na última **[Release](https://github.com/gabrielbolzani/3d_printer_connection_hub/releases/latest)**
2. Extraia e instale manualmente:

```bash
tar -xzf aditivaflow-hub.tar.gz
cd aditivaflow-hub

# Criar virtualenv e instalar dependências
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Iniciar
python app.py
```

Para configurar como serviço systemd permanente, crie o arquivo `/etc/systemd/system/aditivaflow-hub.service`:

```ini
[Unit]
Description=AditivaFlow Hub
After=network.target

[Service]
WorkingDirectory=/opt/aditivaflow-hub
ExecStart=/opt/aditivaflow-hub/venv/bin/python app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now aditivaflow-hub
```

---

## ⚙️ Configuração Inicial

Independentemente do método de instalação, o processo de configuração é o mesmo:

**1. Acesse o Dashboard**
Abra o navegador e acesse:
- `http://localhost:5000` (na mesma máquina)
- `http://IP-DO-SERVIDOR:5000` (de outro dispositivo na rede)

**2. Conecte à AditivaFlow Cloud** *(opcional)*
- Na aba **Authentication**, cole seu *Device Token* copiado do painel [AditivaFlow](https://aditivaflow.com.br)
- Isso habilita envio de telemetria, histórico de impressões e controle remoto pela nuvem

**3. Adicione suas impressoras**
- Clique em **"Nova Impressora"** e preencha:
  - Tipo (Bambu Lab / Klipper / Elegoo) e nome
  - IP local e porta
  - *Se Bambu:* Número de série e Código de Acesso (visível no app Bambu Handy → configurações da impressora)
  - *Opcional:* Platform Token para vincular a impressora ao seu painel AditivaFlow

---

## 💡 Qual método de instalação escolher?

| Cenário | Método recomendado |
|---|---|
| Usuário Windows, desktop, sem conhecimento técnico | **Windows Setup (.exe)** |
| Testes rápidos ou sem instalar permanentemente | **Windows Portátil (.exe)** |
| Raspberry Pi ou servidor Linux pela primeira vez | **Instalador curl** ⭐ |
| Ambiente de produção que exige isolamento máximo | **Docker Compose** |
| Administrador Linux avançado com controle total | **Pacote .tar.gz manual** |
| Desenvolvedor / contribuidor | **Código-fonte (clone do git)** |

---

## 👨‍💻 Rodando a partir do Código-Fonte

Para contribuir ou testar funcionalidades em desenvolvimento:

```bash
git clone https://github.com/gabrielbolzani/3d_printer_connection_hub.git
cd 3d_printer_connection_hub

python -m venv venv
source venv/bin/activate          # Linux/macOS
# venv\Scripts\activate           # Windows

pip install -r requirements.txt
python app.py
```

---

## 📄 Licença e Propriedade Intelectual

Este software está protegido por uma **Licença de Código-Fonte Disponível Proprietária**.

- ✅ Você **pode** visualizar, estudar o código e executar localmente para uso pessoal
- ✅ Você **pode** sugerir melhorias, reportar bugs e enviar Pull Requests
- ❌ Você **não pode** redistribuir, vender ou usar comercialmente sem autorização
- ❌ Você **não pode** criar e publicar obras derivadas sem permissão

Veja o arquivo [LICENSE](./LICENSE) para os termos completos.

**Titular:** Gabriel Forza Juliatti Bolzani  
**Marcas:** Aditivaflow / Aditiva Lab  
**Contato:** gabriel@aditivaflow.com.br  
**Plataforma:** [aditivaflow.com.br](https://aditivaflow.com.br)
