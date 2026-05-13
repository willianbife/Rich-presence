from __future__ import annotations

from datetime import datetime, time as clock_time
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from app.core.models import PresenceConfig, Preset
from app.utils.logger import logger
from app.services.game_integration import GameIntegrationService


class SafeAutomationService(QObject):
    preset_selected = Signal(object)
    config_detected = Signal(object, str)

    def __init__(self) -> None:
        super().__init__()
        self._presets: list[Preset] = []
        self._index = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._process_timer = QTimer(self)
        self._process_timer.timeout.connect(self._start_detection_thread)
        self.start_on_launch = False
        self.scheduled_time: clock_time | None = None
        self.process_detection_enabled = False
        self.game_detection_enabled = False
        self._last_detected_key = ""
        self._detection_lock = threading.Lock()
        self._game_service = GameIntegrationService()

    def configure_presets(self, presets: list[Preset]) -> None:
        self._presets = presets
        self._index = 0

    def start_rotation(self, minutes: int) -> None:
        if not self._presets:
            logger.log("Automacao nao iniciada: nenhum preset salvo.", "warning")
            return
        interval = max(1, minutes) * 60 * 1000
        self._timer.start(interval)
        logger.log(f"Rotacao segura ativada a cada {max(1, minutes)} minuto(s).", "success")

    def stop_rotation(self) -> None:
        self._timer.stop()
        logger.log("Rotacao automatica pausada.", "info")

    def set_process_detection(self, enabled: bool, interval_seconds: int = 15) -> None:
        self.process_detection_enabled = enabled
        if enabled:
            self._process_timer.start(max(15, interval_seconds) * 1000)
            self._start_detection_thread()
            logger.log("Deteccao de processos ativada com intervalo seguro.", "success")
        else:
            self._process_timer.stop()
            self._last_detected_key = ""
            logger.log("Deteccao de processos pausada.", "info")

    def set_schedule(self, hour: int, minute: int) -> None:
        self.scheduled_time = clock_time(hour=max(0, min(hour, 23)), minute=max(0, min(minute, 59)))
        logger.log(f"Horario de ativacao definido para {self.scheduled_time.strftime('%H:%M')}.", "info")

    def should_activate_now(self) -> bool:
        if not self.scheduled_time:
            return False
        now = datetime.now().time()
        return now.hour == self.scheduled_time.hour and now.minute == self.scheduled_time.minute

    def _rotate(self) -> None:
        if not self._presets:
            return
        preset = self._presets[self._index % len(self._presets)]
        self._index += 1
        logger.log(f"Automacao aplicou o preset: {preset.name}.", "info")
        self.preset_selected.emit(preset)

    def _start_detection_thread(self) -> None:
        if not self.process_detection_enabled:
            return
        # Usa uma thread simples para nao travar a UI durante o psutil.process_iter
        thread = threading.Thread(target=self._detect_process_presence, daemon=True)
        thread.start()

    def _detect_process_presence(self) -> None:
        if not self._detection_lock.acquire(blocking=False):
            return
        try:
            # 1. Tenta detecção de jogos primeiro (Prioridade Máxima)
            if self.game_detection_enabled:
                game_result = self._game_service.detect_active_game()
                if game_result:
                    config, exe_key = game_result
                    if exe_key != self._last_detected_key:
                        self._last_detected_key = exe_key
                        logger.log(f"Jogo detectado automaticamente: {exe_key}.", "success")
                        self.config_detected.emit(config, exe_key)
                    return

            # 2. Tenta detecção de processos gerais (Fallback)
            try:
                import psutil
            except Exception:
                self.process_detection_enabled = False
                return

            names: set[str] = set()
            try:
                for proc in psutil.process_iter(["name"]):
                    name = (proc.info.get("name") or "").lower()
                    if name:
                        names.add(name)
            except Exception as exc:
                return

            rules = [
                (("code.exe", "vscode.exe"), "vscode", PresenceConfig("Programando no VS Code", "Editor aberto | foco dev", "code", "VS Code detectado", mood="dev")),
                (("spotify.exe",), "spotify", PresenceConfig("Ouvindo musica", "Spotify aberto | vibe ativa", "music", "Spotify detectado", mood="music")),
                (("valorant.exe", "riotclientservices.exe"), "valorant", PresenceConfig("Jogando Valorant", "Fila gamer | mira ligada", "game", "Valorant detectado", mood="gaming")),
                (("node.exe", "python.exe", "pythonw.exe"), "backend", PresenceConfig("Rodando backend", "Node/Python ativo | APIs", "code", "Backend detectado", mood="dev")),
                (("chrome.exe", "msedge.exe", "firefox.exe"), "browser", PresenceConfig("Navegando/estudando", "Browser aberto | pesquisa", "study", "Navegador detectado", mood="study")),
            ]
            for process_names, key, config in rules:
                if any(name in names for name in process_names):
                    if key != self._last_detected_key:
                        self._last_detected_key = key
                        logger.log(f"Automacao detectou: {key}.", "info")
                        self.config_detected.emit(config, key)
                    return
        finally:
            self._detection_lock.release()
