from __future__ import annotations

from time import monotonic

from PySide6.QtCore import QObject, Signal

from app.core.models import PresenceConfig
from app.utils.logger import logger


class DiscordRPCService(QObject):
    status_changed = Signal(str, bool)

    def __init__(self) -> None:
        super().__init__()
        self._rpc = None
        self._client_id = ""
        self.connected = False
        self._last_status: tuple[str, bool] | None = None
        self._last_payload: dict = {}
        self._last_update_at = 0.0

    @property
    def client_id(self) -> str:
        return self._client_id

    def connect(self, client_id: str) -> bool:
        client_id = client_id.strip()
        if not client_id:
            self._emit_status("Informe um Client ID valido.", False)
            logger.log("Falha ao conectar: Client ID vazio.", "warning")
            return False

        try:
            from pypresence import Presence

            self.disconnect(silent=True)
            self._rpc = Presence(client_id)
            self._rpc.connect()
            self._client_id = client_id
            self.connected = True
            self._emit_status("Conectado ao Discord RPC.", True)
            logger.log("Conexao com Discord RPC realizada.", "success")
            return True
        except Exception as exc:
            self._rpc = None
            self.connected = False
            message = f"Nao foi possivel conectar. Abra o Discord e confira o Client ID. Detalhe: {exc}"
            self._emit_status(message, False)
            logger.log(message, "error")
            return False

    def disconnect(self, silent: bool = False) -> None:
        if self._rpc:
            try:
                self.clear_presence()
                self._rpc.close()
            except Exception:
                pass

        self._rpc = None
        self.connected = False
        self._last_payload = {}
        if not silent:
            self._emit_status("Desconectado.", False)
            logger.log("Discord RPC desconectado.", "info")

    def clear_presence(self) -> None:
        if self.connected and self._rpc:
            try:
                self._rpc.clear()
                logger.log("Presença removida do perfil.", "info")
            except Exception as exc:
                logger.log(f"Erro ao limpar presença: {exc}", "error")

    def update_presence(self, config: PresenceConfig) -> bool:
        if not self.connected or not self._rpc:
            logger.log("Presenca nao enviada: Discord RPC desconectado.", "warning")
            return False

        try:
            payload = config.to_rpc_payload()
            now = monotonic()
            if payload == self._last_payload and now - self._last_update_at < 15:
                return True
            self._rpc.update(**payload)
            self._last_payload = payload
            self._last_update_at = now
            logger.log("Presenca atualizada no Discord.", "success")
            return True
        except Exception as exc:
            logger.log(f"Erro ao atualizar presenca: {exc}", "error")
            self.connected = False
            self._emit_status("Erro ao atualizar presenca.", False)
            return False

    def _emit_status(self, message: str, connected: bool) -> None:
        status = (message, connected)
        if status == self._last_status:
            return
        self._last_status = status
        self.status_changed.emit(message, connected)
