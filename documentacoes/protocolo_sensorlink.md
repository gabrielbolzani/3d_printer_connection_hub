# Protocolo SensorLink 🌐

O **SensorLink** é um protocolo aberto e simplificado para integração de dispositivos IoT personalizados (como ESP32, Arduino com Ethernet, Raspberry Pi, etc.) ao Hub.

Ele funciona no modelo **Poll-based**, onde o Hub é o cliente e o dispositivo IoT é o servidor. O Hub faz requisições HTTP para o IP do dispositivo para ler sensores e enviar comandos.

---

## 1. Arquitetura de Comunicação

1.  **O Hub consulta o dispositivo** periodicamente (conforme intervalo configurado) usando uma requisição `GET /status`.
2.  **O dispositivo responde** com um JSON contendo a telemetria, estado das saídas e entradas.
3.  **Para atuar**, o Hub envia uma requisição `POST /control` com a ação desejada.

---

## 2. Endpoints que o Dispositivo deve Implementar

### 📊 `GET /status`
Retorna o estado atual do dispositivo.

**Exemplo de Resposta (JSON):**
```json
{
    "device": {
        "name": "ESP32 SensorLink",
        "firmware": "1.0.0",
        "uptime_s": 3600
    },
    "telemetry": {
        "inputVac": 127.5,
        "outputVac": 127.1,
        "watts": 250.5,
        "currentA": 1.97,
        "temperature": 32.5,
        "humidity": 45.0,
        "accumulated_kwh": 12.345
    },
    "outputs": [
        {
            "id": "rele_1",
            "name": "Impressora H2D",
            "status": true
        },
        {
            "id": "rele_2",
            "name": "Iluminação",
            "status": false
        }
    ],
    "inputs": [
        {
            "id": "sensor_porta",
            "name": "Porta do Gabinete",
            "status": 1,
            "type": "digital"
        }
    ]
}
```

*Nota: Você pode omitir campos que seu dispositivo não possui. O Hub se adapta aos campos presentes.*

### 🕹️ `POST /control`
Recebe comandos de atuação.

**Payload Enviado pelo Hub (JSON):**
```json
{
    "action": "turn_on",
    "target": "rele_1"
}
```

**Ações Suportadas:**
- `turn_on`: Liga o alvo (target).
- `turn_off`: Desliga o alvo (target).
- `reset_consumption`: Zera o consumo acumulado (se aplicável).

**Resposta Esperada (JSON):**
```json
{
    "success": true,
    "message": "Ação executada com sucesso"
}
```

---

## 3. Exemplo de Código para ESP32 (Arduino IDE)

Aqui está um exemplo básico de como implementar o SensorLink em um ESP32 usando a biblioteca `WebServer`.

```cpp
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>

const char* ssid = "SUA_REDE_WIFI";
const char* password = "SUA_SENHA_WIFI";

WebServer server(80);

// Pinos
const int RELE_1 = 12;
const int SENSOR_PORTA = 13;

// Variáveis simuladas
float accumulated_kwh = 0.0;

void handleStatus() {
  StaticJsonDocument<1024> doc;
  
  // Dados do dispositivo
  JsonObject device = doc.createNestedObject("device");
  device["name"] = "ESP32 SensorLink";
  device["firmware"] = "1.0.0";
  device["uptime_s"] = millis() / 1000;
  
  // Telemetria (Simulada ou lida de sensores reais)
  JsonObject telemetry = doc.createNestedObject("telemetry");
  telemetry["inputVac"] = 127.0;
  telemetry["watts"] = 150.0;
  telemetry["currentA"] = 1.18;
  telemetry["temperature"] = 28.5;
  telemetry["accumulated_kwh"] = accumulated_kwh;
  
  // Saídas
  JsonArray outputs = doc.createNestedArray("outputs");
  JsonObject out1 = outputs.createNestedObject();
  out1["id"] = "rele_1";
  out1["name"] = "Impressora H2D";
  out1["status"] = digitalRead(RELE_1) == HIGH;
  
  // Entradas
  JsonArray inputs = doc.createNestedArray("inputs");
  JsonObject in1 = inputs.createNestedObject();
  in1["id"] = "sensor_porta";
  in1["name"] = "Porta";
  in1["status"] = digitalRead(SENSOR_PORTA);
  in1["type"] = "digital";
  
  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

void handleControl() {
  if (server.hasArg("plain")) {
    String body = server.arg("plain");
    StaticJsonDocument<200> doc;
    deserializeJson(doc, body);
    
    String action = doc["action"];
    String target = doc["target"];
    
    if (target == "rele_1") {
      if (action == "turn_on") digitalWrite(RELE_1, HIGH);
      else if (action == "turn_off") digitalWrite(RELE_1, LOW);
    }
    
    server.send(200, "application/json", "{\"success\":true}");
  } else {
    server.send(400, "application/json", "{\"success\":false}");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(RELE_1, OUTPUT);
  pinMode(SENSOR_PORTA, INPUT_PULLUP);
  
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi conectado!");
  Serial.print("IP: "); Serial.println(WiFi.localIP());
  
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/control", HTTP_POST, handleControl);
  server.begin();
}

void loop() {
  server.handleClient();
  // Simula ganho de consumo
  accumulated_kwh += 0.0001;
  delay(1);
}
```
