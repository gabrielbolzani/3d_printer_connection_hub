# 🚀 AditivaFlow Printer Hub

O **AditivaFlow Hub** é um gateway poderoso e unificado para transformar o gerenciamento das suas impressoras 3D. Ele conecta impressoras locais de diferentes marcas (Bambu Lab, Klipper, Elegoo) à plataforma **AditivaFlow**, permitindo monitoramento remoto, telemetria em tempo real e controle centralizado.

Projetado para ser versátil, o Hub pode rodar como um serviço de background no Linux, um aplicativo desktop no Windows ou como um Add-on dentro do Home Assistant.

---

## 📦 Versões Disponíveis

### 🪟 Windows (Desktop App)
Ideal para quem utiliza um PC ou Servidor Windows.

*   **Instalação (Instalador Automático):** 
    1.  Baixe o `AditivaFlowHub-Setup.exe` na aba [Releases](https://github.com/gabrielbolzani/3d_printer_connection_hub/releases).
    2.  Ao executar, caso o Windows mostre **"O Windows protegeu o seu computador"**, clique em **"Mais informações"** e depois em **"Executar assim mesmo"** (o aplicativo é seguro, mas como não possui certificado digital pago, o SmartScreen exibe este alerta).
    3.  Siga as instruções para instalar. O Hub criará atalhos e pode ser configurado para iniciar automaticamente com o Windows.
*   **Instalação (Portátil):** 
    1.  Baixe o `AditivaFlowHub-Windows.exe` e execute diretamente onde desejar.

### 🐧 Linux (Server/Raspberry Pi)
A melhor opção para máquinas dedicadas. Pode ser executado nativamente via script ou, preferencialmente, pelo Docker.

*   **Instalação via Docker (Recomendado):**
    ```bash
    git clone https://github.com/gabrielbolzani/3d_printer_connection_hub.git
    cd 3d_printer_connection_hub
    docker-compose up -d --build
    ```

*   **Instalação Nativa via Terminal (CURL):**
    ```bash
    sudo curl -sSL https://raw.githubusercontent.com/gabrielbolzani/3d_printer_connection_hub/main/deployments/linux/install.sh | bash
    ```

---

## 🛠️ Funcionalidades

*   **Dashboard Unificado:** Visualize todas as suas impressoras em uma única tela local (`http://localhost:5000`).
*   **Multi-Driver:** Suporte nativo para:
    *   **Bambu Lab:** X1, P1, A1 (via Cloud ou Local MQTT).
    *   **Klipper / Moonraker:** Voron, RatRig, Ender (com Klipper).
    *   **Elegoo:** Resina (Saturn 3 Ultra e similares).
*   **Sincronização Cloud:** Envio automático de telemetria, histórico de impressão e imagens da câmera para o AditivaFlow.
*   **Monitoramento de Sistema:** Acompanhe o uso de CPU, RAM e Rede da máquina host.

---

## ⚙️ Configuração Inicial

1.  **Acesse o Hub:** Abra `http://localhost:5000` no seu navegador.
2.  **Autenticação:** Na aba de Configurações, insira seu `Device Token` do AditivaFlow.
3.  **Adicionar Impressoras:** Informe o IP e as credenciais (Serial/Access Code para Bambu) de cada máquina.
4.  **Pronto!** Suas impressoras começarão a aparecer no dashboard local e na nuvem.

---

## 👨‍💻 Para Desenvolvedores

Se deseja rodar a partir do código fonte:

1.  Clone o repositório: `git clone https://github.com/gabrielbolzani/3d_printer_connection_hub.git`
2.  Crie um ambiente virtual: `python -m venv venv`
3.  Instale requisitos: `pip install -r requirements.txt`
4.  Inicie: `python app.py`

---

## 📄 Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais informações.

---
**Desenvolvido por Gabriel Bolzani para [AditivaFlow](https://aditivaflow.com.br)**
