import socket
import json
from datetime import datetime, timedelta
import logging

_LOGGER = logging.getLogger(__name__)

class ElegooClient:
    def __init__(self, ip: str, port: int = 3000, timeout: int = 5):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.buff_size = 4096

    def _send_command(self, command: str) -> dict:
        """Envia um comando para a impressora e retorna a resposta em JSON."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            sock.sendto(command.encode(), (self.ip, self.port))
            response, _ = sock.recvfrom(self.buff_size)
            return json.loads(response.decode())
        except socket.timeout:
            _LOGGER.debug("Timeout: Nenhuma resposta recebida da impressora em %s", self.ip)
            return {}
        except Exception as e:
            _LOGGER.error("Erro ao comunicar com a impressora %s: %s", self.ip, e)
            return {}
        finally:
            sock.close()

    def get_data(self) -> dict:
        """Busca todos os dados relevantes da impressora."""
        response = self._send_command("M99999")
        if not response:
            return None
        
        data = response.get("Data", {})
        attributes = data.get("Attributes", {})
        status = data.get("Status", {})
        print_info = status.get("PrintInfo", {})

        # Status translation
        status_code = status.get("CurrentStatus", -1)
        status_map = {0: "Idle", 1: "Printing", 2: "Paused", 3: "Error"}
        status_text = status_map.get(status_code, "Unknown")

        # Progress calculation
        current_layer = print_info.get("CurrentLayer", 0)
        total_layers = print_info.get("TotalLayer", 0)
        elapsed_ticks = print_info.get("CurrentTicks", 0)
        total_ticks = print_info.get("TotalTicks", 0)
        
        percentage = (current_layer / total_layers * 100) if total_layers > 0 else 0
        
        return {
            "machine_name": attributes.get("MachineName", "Unknown"),
            "firmware": attributes.get("FirmwareVersion", "Unknown"),
            "status": status_text,
            "filename": print_info.get("Filename", ""),
            "current_layer": current_layer,
            "total_layers": total_layers,
            "progress": round(percentage, 2),
            "remaining_time": self._ticks_to_time(total_ticks - elapsed_ticks) if total_ticks > elapsed_ticks else "0h 0m 0s",
            "finish_time": self._calculate_finish_time(total_ticks - elapsed_ticks) if total_ticks > elapsed_ticks else "N/A"
        }

    def pause(self):
        """Pausa a impressão atual."""
        return self._send_command("M25")

    def resume(self):
        """Retoma a impressão pausada."""
        return self._send_command("M24")

    def stop(self):
        """Para/Cancela a impressão atual."""
        return self._send_command("M33")

    def _ticks_to_time(self, ticks: int) -> str:
        seconds = max(0, ticks // 1000)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f"{hours}h {minutes}m {seconds}s"

    def _calculate_finish_time(self, remaining_ticks: int) -> str:
        if remaining_ticks <= 0:
            return "Finalizado"
        remaining_seconds = remaining_ticks / 1000
        finish_datetime = datetime.now() + timedelta(seconds=remaining_seconds)
        return finish_datetime.strftime("%H:%M:%S - %d/%m/%y")
