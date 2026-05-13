from __future__ import annotations

try:
    import psutil
except Exception:
    psutil = None

from app.core.models import PresenceConfig
from app.utils.logger import logger


class GameIntegrationService:
    GAME_MAP = {
        "cs2.exe": ("Counter-Strike 2", "cs2", "gaming"),
        "csgo.exe": ("CS:GO", "csgo", "gaming"),
        "valorant.exe": ("Valorant", "valorant", "gaming"),
        "riotclientservices.exe": ("Riot Client", "riot", "gaming"),
        "league of legends.exe": ("League of Legends", "lol", "gaming"),
        "leagueclient.exe": ("League of Legends (Client)", "lol", "gaming"),
        "minecraft.exe": ("Minecraft", "minecraft", "gaming"),
        "javaw.exe": ("Minecraft (Java)", "minecraft", "gaming"),
        "robloxplayerbeta.exe": ("Roblox", "roblox", "gaming"),
        "gta5.exe": ("Grand Theft Auto V", "gta5", "gaming"),
        "fivem_b2699_gta5.exe": ("FiveM / GTA V", "fivem", "gaming"),
        "fivem.exe": ("FiveM", "fivem", "gaming"),
        "stardew valley.exe": ("Stardew Valley", "stardew", "gaming"),
        "overwatch.exe": ("Overwatch 2", "overwatch", "gaming"),
        "fortniteclient-win64-shipping.exe": ("Fortnite", "fortnite", "gaming"),
        "cod.exe": ("Call of Duty", "cod", "gaming"),
        "steam.exe": ("Navegando na Steam", "steam", "gaming"),
    }

    def detect_active_game(self) -> tuple[PresenceConfig, str] | None:
        if psutil is None:
            logger.log("psutil nao esta instalado; deteccao de jogos indisponivel.", "warning")
            return None

        try:
            active_processes = {
                (process.info.get("name") or "").lower()
                for process in psutil.process_iter(["name"])
            }

            for exe, (name, asset, mood) in self.GAME_MAP.items():
                if exe.lower() in active_processes:
                    config = PresenceConfig(
                        details=f"Jogando {name}",
                        state="Partida em andamento",
                        large_image=asset,
                        large_text=name,
                        small_image="studio_small",
                        small_text="Detectado via Presence Studio",
                        mood=mood,
                    )
                    return config, exe
        except Exception as exc:
            logger.log(f"Erro na deteccao de jogos: {exc}", "error")

        return None
