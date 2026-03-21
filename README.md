# 🚀 AditivaFlow Printer Hub

O **AditivaFlow Hub** é a ponte inteligente entre a sua fazenda de impressoras 3D local e a nuvem. Ele atua como um gateway centralizado: você o instala em um único computador ou servidor (Raspberry Pi, PC Windows, Servidor Linux) na mesma rede Wi-Fi/Local das suas impressoras, e ele se encarrega de conectar, traduzir e enviar toda a telemetria, streaming de câmera e controle diretamente para a plataforma [AditivaFlow](https://aditivaflow.com.br).

Com o Hub configurado, suas máquinas descentralizadas (de diferentes marcas e sistemas) ganham uma **interface única, padronizada e acessível de qualquer lugar do mundo** via nuvem da AditivaFlow.

---

## 🖨️ Equipamentos Compatíveis

O ecossistema de impressão 3D é diverso, e o Hub resolve o problema de diferentes linguagens de comunicação. Atualmente, o Hub possui Suporte Nativo Plug-and-Play para os seguintes equipamentos:

1. **Bambu Lab (Série X, Série P e Série A)**
   - Integração via Cloud ou Modo LAN (MQTT Local).
   - Suporte a leitura completa do sistema AMS (umidade, rolos, cor).
   - Leitura de câmeras e atualização de status em tempo real.
   - Sincronização inteligente dos avisos de erro (HMS).
2. **Sistema Klipper (via Moonraker)**
   - Compatível com qualquer impressora rodando Klipper (Voron, RatRig, Ender adaptada, Creality K1, etc).
   - Controle nativo (Pausar, Retomar, Cancelar, Ajustar FANS), leitura macro, sensores e captura de Câmera Web via Moonraker API.
3. **Elegoo (Resina)**
   - Compatível com impressoras Elegoo da série Saturn (Saturn 3 Ultra, etc) e Mars conectadas à rede.
   - Sincronização de status da resina e andamento da impressão via rede.

---

## 📦 Como Instalar (Opções de Lançamento)

Para facilitar a implantação, oferecemos arquivos pré-compilados e configurados na aba **[Releases](https://github.com/gabrielbolzani/3d_printer_connection_hub/releases)** deste repositório. Escolha o melhor para sua infraestrutura:

### 🪟 Windows (Ideal para usuários comuns e PCs desktop)

Se você tem um computador com Windows na mesma rede das impressoras e que fica sempre ligado:

1. **Instalador Automático (Recomendado): `AditivaFlowHub-Setup.exe`**
   - **Como usar:** Baixe e execute. Ele abrirá a tradicional tela de *Avançar > Instalar*. Ele configurará o Hub na sua máquina de forma totalmente automática, criará ícones e o iniciará em background (inclusve junto ao próprio Windows).
   - *Aviso:* Como os executáveis Open Source ainda não são assinados com um certificado corporativo internacional, o Windows SmartScreen frequentemente exibe um aviso em uma tela azul dizendo: *"O Windows protegeu o seu computador"*. Você só precisa clicar em **Mais informações** e depois selecionar a opção visível de **Executar assim mesmo**. Fique tranquilo, todos os nossos arquivos das Releases do GitHub são seguros e verificados.
   
2. **Executável Portátil: `AditivaFlowHub-Windows.exe`**
   - **Como usar:** Basta fazer o download do arquivo executável, alojá-lo numa pasta e abrí-lo quando for usar a ferramenta. Útil se você estiver realizando simulações, homologações ou não quiser deixar nada salvo na inicialização do Windows do seu servidor.

### 🐧 Linux (Ideal para Servidores Linux e Raspberry Pi)

A opção de menor consumo de energia e menor manutenção, caso esteja usando um computador embarcado e sem interfaces de vídeo dedicadas de forma embutida (headless).

1. **Containers via Docker (A nossa recomendação máxima)**
   Rodar no formato em container isola completamente o Hub, impedindo que conflito de bibliotecas Python quebre o sistema da sua base operacional.

   **Passo-a-passo:**
   - Use o GIT a fim de copiar a base atualizada em uma nova pasta:
   ```bash
   git clone https://github.com/gabrielbolzani/3d_printer_connection_hub.git
   cd 3d_printer_connection_hub
   docker-compose up -d --build
   ```
   - O argumento `-d` roda o container e libera o seu terminal. A partir de então a subida da porta web estará ativa na `5000` para navegação.

2. **Baixando o Pacote Linux Direto (`aditivaflow-hub.tar.gz`)**
   A aba de Releases disponibiliza também os scripts puristas dentro desse .zip (tar.gz). Você pode baixar, extrair em nível raiz e rodar as engrenagens sem auxílio de container executando manualmente as instruções virtuais: `pip install -r requirements.txt ; python app.py`. O uso dessa versão é recomendada se você sabe instalar e ativá-la pelo `SystemD` da sua máquina e configurar o auto-init.

3. **Script Nativo via CURL (Automático)**
   Script pré-agendado que lida com a inicialização direta de requisitos apt e a montagem direta como Serviço do SystemD:
   ```bash
   sudo curl -sSL https://raw.githubusercontent.com/gabrielbolzani/3d_printer_connection_hub/main/deployments/linux/install.sh | bash
   ```

---

## ⚙️ O que Configurar Inicialmente?

Não importa como você instalou (Windows Desktop, Linux nativo ou Docker), tudo opera local e é super fácil configurar.

1. **Acessando o Dashboard Local:** No servidor local onde completou a configuração, abra um simples navegador e vá para o portal de administração do HUB: `http://localhost:5000` (ou caso você esteja configurando no Raspberry via Laptop na rede use: `http://NÚMERO-DO-IP-DO-SERVER:5000`).
2. **Autenticação com a Nuvem:** Para que o controle ganhe asas e envie os relatórios pro seu provedor da nuvem, logue na sua interface da AditivaFlow Online, copie o seu `Token / Device Token`. Abra o painel lateral do seu aplicativo HUB na aba **Authentication** e salve ele ali para sempre. Essa trava vai garantir a criptografia e proteção da sua banda de envio.
3. **Adicionando suas Máquinas Locais:** Volte para a Aba `Printers`, clique em Nova Impressora. E você inserirá:
   - Tipo de máquina e Nome.
   - Seu Local IP / Porta.
   - *Se for Bambu:* Código de Acesso do app do celular, e o serial num.
   - *Opcional*: Informar no fim a chave de `Platform Token` para se juntar à contabilidade automatizada da sua impressora na base virtual do AditivaFlow Cloud.

*Pronto! Os painéis ficarão em sincronia e telemetria estará pulsando pela máquina da sua rede à AditivaFlow System Cloud!*

---

## 👨‍💻 Contribuindo e Rodando a partir do Código-Fonte

Desenvolvedores ou entusiastas que queiram contribuir com melhorias:
1. Faça o clone normal do Git: `git clone https://github.com/gabrielbolzani/3d_printer_connection_hub.git`
2. Crie a venv local: `python -m venv venv` 
3. Instale os requerimentos abertos: `pip install -r requirements.txt`
4. Suba o Hub: `python app.py`

---

## 📄 Informações e Licenças

Software desenhado e distribuído sob a licença **MIT**, moldado para apoiar Makers, Fazendas de Impressão de alta densidade e o belíssimo ecosistema que a Comunidade Livre impulsiona.

**Direção Geral e Desenvolvimento: Gabriel Bolzani**  
Para mais detalhes sobre as instâncias da Nuvem e Painéis da Web da sua fábrica acesse:  [AditivaFlow](https://aditivaflow.com.br)
