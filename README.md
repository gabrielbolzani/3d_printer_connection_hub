# Hub de Conexão de Impressoras 3D - AditivaFlow

Um gateway centralizado e poderoso projetado para complementar a plataforma **AditivaFlow**. Este projeto permite gerenciar e unificar impressoras 3D de diferentes fabricantes (Bambu Lab, Klipper/Moonraker, Elegoo) em um dashboard único e unificado.

Projetado para rodar em modo "headless" (sem monitor) em uma máquina dedicada (como um Raspberry Pi ou Mini PC), mas acessível de qualquer dispositivo através de uma interface web responsiva.

## 🚀 Funcionalidades Principais

*   **Integração AditivaFlow**: Atua como uma ponte para conectar suas impressoras locais à nuvem e serviços da AditivaFlow.
*   **Dashboard Unificado**: Monitore múltiplas impressoras em tempo real em uma única tela. Chega de alternar abas entre diferentes IPs.
*   **Suporte Multi-Marca**: Integração perfeita de impressoras de diferentes ecossistemas:
    *   **Bambu Lab**: Monitoramento completo de status via MQTT seguro (SSL).
    *   **Klipper / Moonraker**: Integração padrão para Vorons, RatRig, Creality K1/Max (com root) e outras máquinas baseadas em Klipper.
    *   **Elegoo (Série Saturn)**: Comunicação direta UDP para impressoras de resina como a Saturn 3 Ultra.
*   **Monitoramento do Sistema**: Rastreamento integrado de recursos da máquina host (CPU, RAM, Disco, Rede e I/O da Aplicação) para garantir operação estável.
*   **Design Responsivo**: Interface amigável para dispositivos móveis que funciona perfeitamente em desktops, tablets e smartphones.
*   **Armazenamento Seguro**: Gerencia com segurança os tokens de integração para conectividade externa.

## 🖨️ Hardware Suportado

A aplicação inclui atualmente drivers para:
*   **Bambu Lab**: X1C, P1S, A1, A1 Mini (requer Código de Acesso e Serial).
*   **Klipper**: Qualquer impressora rodando API Moonraker (ex: Voron, Creality K1/Max).
*   **Elegoo**: Testado com Saturn 3 Ultra (Implementação de referência para sistemas Chitu).

## 🛠️ Instalação

### Pré-requisitos
*   Python 3.8 ou superior
*   Gerenciador de pacotes `pip`

### Passos

1.  **Clone o Repositório**
    ```bash
    git clone https://github.com/gabrielbolzani/3d_printer_connection_hub.git
    cd 3d_printer_connection_hub
    ```

2.  **Instale as Dependências**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Execute a Aplicação**
    ```bash
    python app.py
    ```

4.  **Acesse o Dashboard**
    Abra seu navegador e acesse:
    `http://localhost:5000` ou `http://<ip-da-sua-maquina>:5000`

## ⚙️ Configuração

### Adicionando uma Impressora
1.  Navegue até a aba **Printers** (Impressoras) na barra lateral.
2.  Clique no botão **Add Printer** (Adicionar Impressora) no canto superior direito.
3.  Selecione o tipo da impressora (Bambu, Moonraker ou Elegoo).
4.  Insira os detalhes necessários (Endereço IP, Número de Série, Código de Acesso, etc.).
5.  Clique em **Add**. A impressora aparecerá instantaneamente no dashboard.

### Monitoramento do Sistema
Navegue até a aba **System Monitor** para ver estatísticas em tempo real da máquina host, incluindo o uso específico de recursos da aplicação Python Hub.

## 🏗️ Arquitetura

O projeto é construído com:
*   **Backend**: Python (Flask) para o servidor web e API.
*   **Frontend**: HTML5, CSS3 (Design responsivo customizado), JavaScript (Fetch API, Chart.js).
*   **Protocolos**: MQTT (Bambu), HTTP REST (Moonraker), UDP (Elegoo).

## 🤝 Contribuição

Contribuições são bem-vindas! Se você quiser adicionar suporte para uma nova marca de impressora:
1.  Faça um Fork do repositório.
2.  Crie uma nova classe de driver herdando de `BasePrinter` em `printer_drivers.py`.
3.  Atualize a função factory `create_printer`.
4.  Envie um Pull Request.

## 📄 Licença

MIT License - sinta-se à vontade para usar e modificar para seus próprios setups.
