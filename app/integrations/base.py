from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IntegrationInfo:
    name: str
    description: str
    status: str = "Mockup"
    enabled: bool = False


class IntegrationAdapter:
    info = IntegrationInfo(name="Base", description="Adapter base")

    def connect(self) -> bool:
        return False

    def read_activity(self) -> dict[str, str]:
        return {}


AVAILABLE_INTEGRATIONS = [
    IntegrationInfo("Spotify", "Preparado para transformar música atual em presença."),
    IntegrationInfo("Steam", "Base para detectar jogos e status de atividade."),
    IntegrationInfo("League of Legends", "Estrutura para exibir partida, campeão e fila."),
    IntegrationInfo("Valorant", "Estrutura para status de partida e agente."),
    IntegrationInfo("APIs externas", "Ponto de expansão para webhooks e APIs públicas."),
]
