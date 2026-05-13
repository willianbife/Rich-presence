from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.core.models import PresenceButton, PresenceConfig
from app.utils.logger import logger


GEMINI_MODEL_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent?key={api_key}"
)


@dataclass(frozen=True)
class Intent:
    mood: str
    topic: str
    action: str
    style: str


class AIGeneratorService:
    def generate(self, prompt: str, mode: str = "generate", current: PresenceConfig | None = None) -> PresenceConfig:
        prompt = prompt.strip()
        if not prompt and current is None:
            return self._fallback("presenca criativa para Discord", "cyberpunk", mode, current)

        api_key = self._api_key()
        if not api_key:
            logger.log("GEMINI_API_KEY ausente. Usando gerador local inteligente.", "warning")
            return self._fallback(prompt or current.details, current.mood if current else "cyberpunk", mode, current)

        try:
            raw = self._call_gemini(api_key, prompt, mode, current)
            data = self._extract_json(raw)
            return self._config_from_ai(data, current)
        except urllib.error.HTTPError as exc:
            if exc.code in {403, 429}:
                logger.log("Gemini recusou ou limitou a chamada. Usando fallback local.", "warning")
            else:
                logger.log(f"Falha HTTP na Gemini ({exc.code}). Usando fallback local.", "warning")
        except Exception as exc:
            logger.log(f"IA retornou algo invalido ({exc}). Usando fallback local.", "warning")

        return self._fallback(prompt or (current.details if current else ""), current.mood if current else "cyberpunk", mode, current)

    def _api_key(self) -> str:
        value = os.getenv("GEMINI_API_KEY", "").strip()
        if self._looks_real_key(value):
            return value
        for env_path in self._env_candidates():
            try:
                env_file = open(env_path, "r", encoding="utf-8")
            except OSError:
                continue
            with env_file:
                for line in env_file:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        value = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if self._looks_real_key(value):
                            return value
        return ""

    def _env_candidates(self) -> list[str]:
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
        return [os.path.join(base, ".env"), os.path.join(os.getcwd(), ".env")]

    def _looks_real_key(self, value: str) -> bool:
        placeholders = {"sua_chave_aqui", "cole_sua_chave_aqui", "your_api_key_here"}
        return bool(value and value.lower() not in placeholders and len(value) > 20)

    def _call_gemini(self, api_key: str, prompt: str, mode: str, current: PresenceConfig | None) -> str:
        system = """
Voce e um assistente especializado em Discord Rich Presence.
Responda somente JSON valido, sem markdown, sem comentarios e sem texto fora do JSON.

Schema obrigatorio:
{
  "title": "nome curto do preset",
  "details": "linha principal, maximo 80 caracteres",
  "state": "linha secundaria, maximo 80 caracteres",
  "large_text": "tooltip da imagem grande",
  "small_text": "tooltip da imagem pequena",
  "large_image": "",
  "small_image": "",
  "rotating_phrases": ["3 a 8 frases curtas"],
  "buttons": [{"label": "GitHub", "url": "https://github.com/"}],
  "mood": "dev|study|gaming|music|professional|cyberpunk|dark|funny"
}

Regras:
- Entenda intencao, nao copie o pedido literalmente.
- Se o usuario pedir para ativar, conectar ou aparecer no perfil, gere a presenca ideal; o app executa a conexao.
- Se pedir para mudar descricao, altere details.
- Se pedir status/estado, altere state.
- Se pedir melhorar, preserve a ideia atual e deixe mais natural.
- Use portugues natural, curto e bom para Discord.
- Nao invente URL pessoal. Use no maximo 2 botoes http/https.
- Evite frases genericas como "quero que".
""".strip()
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": system},
                        {
                            "text": json.dumps(
                                {
                                    "mode": mode,
                                    "user_request": prompt,
                                    "current_presence": current.to_dict() if current else {},
                                },
                                ensure_ascii=False,
                            )
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.55,
                "topP": 0.9,
                "maxOutputTokens": 900,
                "responseMimeType": "application/json",
            },
        }
        request = urllib.request.Request(
            GEMINI_MODEL_URL.format(api_key=api_key),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload["candidates"][0]["content"]["parts"][0]["text"]

    def _extract_json(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Resposta da IA nao e um objeto JSON.")
        return data

    def _config_from_ai(self, data: dict[str, Any], current: PresenceConfig | None = None) -> PresenceConfig:
        buttons = []
        for item in data.get("buttons", []):
            if isinstance(item, dict):
                buttons.append(PresenceButton(str(item.get("label", ""))[:32], str(item.get("url", ""))))
        while len(buttons) < 2:
            buttons.append(PresenceButton())

        phrases = data.get("rotating_phrases", [])
        if not isinstance(phrases, list):
            phrases = []

        return PresenceConfig(
            details=self._limit(data.get("details") or data.get("title") or (current.details if current else ""), 80),
            state=self._limit(data.get("state") or (current.state if current else ""), 80),
            large_image=self._limit(data.get("large_image", ""), 64),
            large_text=self._limit(data.get("large_text", ""), 80),
            small_image=self._limit(data.get("small_image", ""), 64),
            small_text=self._limit(data.get("small_text", ""), 80),
            rotating_phrases=[self._limit(str(item), 80) for item in phrases if str(item).strip()][:8],
            buttons=buttons[:2],
            mood=self._limit(data.get("mood", "cyberpunk"), 32),
        )

    def _fallback(self, prompt: str, mood: str, mode: str, current: PresenceConfig | None) -> PresenceConfig:
        intent = self._analyze(prompt, mood, mode, current)
        profile = self._profiles()[intent.mood]

        details = self._details_for(intent, profile, current)
        state = self._state_for(intent, profile, current)
        if mode == "phrases":
            details = current.details if current and current.details else details
            state = current.state if current and current.state else state
        if mode == "improve" and current:
            details = self._polish(current.details or details, intent)
            state = self._polish(current.state or state, intent, secondary=True)

        return PresenceConfig(
            details=details,
            state=state,
            large_image=profile["large_image"],
            large_text=profile["large_text"],
            small_image="studio_small",
            small_text="Online no Presence Studio",
            rotating_phrases=self._phrases(intent, profile),
            buttons=self._buttons(intent),
            mood=intent.mood,
        )

    def _analyze(self, prompt: str, default_mood: str, mode: str, current: PresenceConfig | None) -> Intent:
        text = self._normalize(prompt)
        mood_scores = {
            "dev": ["cod", "program", "python", "node", "api", "debug", "terminal", "github", "vscode", "backend", "frontend"],
            "study": ["estud", "aula", "prova", "faculdade", "escola", "leitura", "pesquisa", "curso", "aprend"],
            "gaming": ["jog", "game", "valorant", "league of legends", "lol", "ranked", "partida", "minecraft", "steam", "cs2", "roblox"],
            "music": ["musica", "spotify", "playlist", "ouvindo", "som", "beat", "album"],
            "professional": ["profissional", "trabalho", "cliente", "reuniao", "projeto", "produtiv", "freela"],
            "dark": ["dark", "sombrio", "minimal", "preto", "serio"],
            "funny": ["meme", "shitpost", "engrac", "zoeira", "caos"],
            "cyberpunk": ["cyber", "neon", "futur", "hacker", "terminal"],
        }
        mood = current.mood if current and current.mood else (default_mood or "cyberpunk")
        best_score = 0
        for candidate, words in mood_scores.items():
            score = sum(1 for word in words if word in text)
            if score > best_score:
                best_score = score
                mood = candidate

        if mode == "phrases":
            action = "phrases"
        elif mode == "improve" or any(word in text for word in ["melhor", "refina", "deixa mais bonito", "aprimora"]):
            action = "improve"
        elif any(word in text for word in ["descricao", "details", "linha principal"]):
            action = "details"
        elif any(word in text for word in ["estado", "status", "state", "linha secundaria"]):
            action = "state"
        else:
            action = "generate"

        style = "clean"
        if any(word in text for word in ["profissional", "serio", "clean", "limpo"]):
            style = "professional"
        elif any(word in text for word in ["engrac", "meme", "shitpost", "zoeira", "imbecil", "idiota", "tosco", "zoado"]):
            style = "funny"
        elif any(word in text for word in ["dark", "sombrio", "minimal"]):
            style = "dark"
        elif any(word in text for word in ["cyber", "neon", "futur"]):
            style = "cyberpunk"

        topic = self._extract_topic(prompt)
        return Intent(mood=mood if mood in self._profiles() else "cyberpunk", topic=topic, action=action, style=style)

    def _profiles(self) -> dict[str, dict[str, str]]:
        return {
            "dev": {"details": "Codando no modo foco", "state": "APIs | Debug | Build", "large_image": "code", "large_text": "Ambiente dev ativo"},
            "study": {"details": "Estudando com foco", "state": "Pesquisa | Notas | Evolucao", "large_image": "study", "large_text": "Modo estudo"},
            "gaming": {"details": "Jogando uma partida", "state": "Fila ativa | GG", "large_image": "game", "large_text": "Modo gamer"},
            "music": {"details": "Ouvindo musica", "state": "Playlist ligada | Vibe boa", "large_image": "music", "large_text": "Som ambiente"},
            "professional": {"details": "Trabalhando em projeto", "state": "Planejamento | Execucao", "large_image": "work", "large_text": "Modo profissional"},
            "cyberpunk": {"details": "Cyber Terminal", "state": "Neon | IA | Discord RPC", "large_image": "cyber", "large_text": "Modo neon"},
            "dark": {"details": "Modo dark ativado", "state": "Foco silencioso | Minimal", "large_image": "dark", "large_text": "Dark workspace"},
            "funny": {"details": "Compilando ideias suspeitas", "state": "Caos controlado | 0 bugs talvez", "large_image": "meme", "large_text": "Modo shitpost"},
        }

    def _details_for(self, intent: Intent, profile: dict[str, str], current: PresenceConfig | None) -> str:
        topic = intent.topic
        if intent.action == "state" and current and current.details:
            return current.details
        if topic:
            if intent.mood == "gaming" and intent.style == "funny":
                funny_games = {
                    "League of Legends": "Perdendo PDL no LoL",
                    "Valorant": "Errando pixel no Valorant",
                    "Minecraft": "Minerando sem plano",
                    "Roblox": "Aprontando no Roblox",
                    "Steam": "Comprando jogo que nao vou zerar",
                }
                return self._limit(funny_games.get(topic, f"Jogando {topic} sem garantia"), 80)
            templates = {
                "dev": f"Codando {topic}",
                "study": f"Estudando {topic}",
                "gaming": f"Jogando {topic}",
                "music": f"Ouvindo {topic}",
                "professional": f"Trabalhando em {topic}",
                "funny": f"Sobrevivendo a {topic}",
            }
            return self._limit(templates.get(intent.mood, topic.capitalize()), 80)
        return profile["details"]

    def _state_for(self, intent: Intent, profile: dict[str, str], current: PresenceConfig | None) -> str:
        if intent.action == "details" and current and current.state:
            return current.state
        states = {
            "dev": "Python | APIs | Debug",
            "study": "Foco total | Aprendizado",
            "gaming": "Partida em andamento",
            "music": "Playlist ligada | Vibe boa",
            "professional": "Organizando ideias em entrega",
            "cyberpunk": "Discord RPC | IA | Neon",
            "dark": "Foco silencioso | Dark mode",
            "funny": "Bug nenhum, confia",
        }
        if intent.mood == "gaming" and intent.style == "funny":
            return "SoloQ mentalmente estavel"
        return states.get(intent.mood, profile["state"])

    def _phrases(self, intent: Intent, profile: dict[str, str]) -> list[str]:
        phrase_bank = {
            "dev": ["Debugando o impossivel", "Buildando sem travar o PC", "Commitando progresso", "Transformando cafe em codigo"],
            "study": ["Revisando com calma", "Mais uma pagina vencida", "Aprendizado em andamento", "Foco antes da recompensa"],
            "gaming": ["Fila puxada", "GG em construcao", "Partida em andamento", "Modo clutch ativado"],
            "music": ["Playlist no ponto", "Volume mental ajustado", "Vibe em loop", "Som ligado, foco tambem"],
            "professional": ["Planejando a entrega", "Modo produtividade", "Organizando prioridades", "Construindo com calma"],
            "cyberpunk": ["Neon ligado", "Terminal respirando", "IA no painel", "Cidade acordada"],
            "dark": ["Foco no escuro", "Minimal e direto", "Silencio produtivo", "Dark mode permanente"],
            "funny": ["Compilando desculpas", "Zero bugs na imaginacao", "Deploy da bagunca", "Caos com estilo"],
        }
        phrases = phrase_bank.get(intent.mood, [profile["details"], profile["state"]])
        if intent.mood == "gaming" and intent.style == "funny":
            topic = intent.topic or "o jogo"
            phrases = [
                f"Sofrendo em {topic}",
                "Culpando o matchmaking",
                "Prometi jogar serio",
                "GG moral em andamento",
                "Meu time acredita, eu nao",
            ]
        if intent.topic and not (intent.mood == "gaming" and intent.style == "funny"):
            phrases = [f"{phrases[0]}: {intent.topic}", *phrases[1:]]
        return [self._limit(item, 80) for item in phrases[:6]]

    def _buttons(self, intent: Intent) -> list[PresenceButton]:
        if intent.mood == "dev":
            return [PresenceButton("GitHub", "https://github.com/"), PresenceButton("Projeto", "https://example.com/")]
        return [PresenceButton(), PresenceButton()]

    def _extract_topic(self, prompt: str) -> str:
        known = self._known_topic(prompt)
        if known:
            return known

        text = prompt.strip()
        cleanup = [
            r"\bcoloque de uma forma\b", r"\bde uma forma\b", r"\bforma\b",
            r"\bimbecil\b", r"\bidiota\b", r"\btosca?\b", r"\bzoada?\b",
            r"\bquero que\b", r"\bpor favor\b", r"\bative\b", r"\bativar\b", r"\bconecte\b",
            r"\bconectar\b", r"\bcoloca(?:r)?\b", r"\baparecer\b", r"\bno meu perfil\b",
            r"\bperfil\b", r"\brich presence\b", r"\bpresence\b", r"\bpresen[cç]a\b",
            r"\bdeixando\b", r"\bdeixar\b", r"\bestou\b", r"\beu estou\b", r"\bagora\b",
            r"\bdiscord\b", r"\bmuda(?:r)?\b", r"\baltera(?:r)?\b", r"\bdescri[cç][aã]o\b",
            r"\bdetails\b", r"\bfaz(?:er)?\b", r"\bgera(?:r)?\b", r"\bfrases?\b",
            r"\brotativas?\b", r"\bpra\b", r"\bpara\b", r"\bprofissional\b",
            r"\bcyberpunk\b", r"\bcyber\b", r"\bque\b", r"\bjogando\b",
        ]
        for pattern in cleanup:
            text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip(" ,.-")
        text = re.sub(r"^(a|o|um|uma)\s+", "", text, flags=re.IGNORECASE).strip()
        if len(text) < 3:
            return ""
        lowered = self._normalize(text)
        if "codando" in lowered or "programando" in lowered:
            return "no VS Code"
        if "trabalhando em " in lowered:
            return re.split(r"trabalhando em\s+", text, flags=re.IGNORECASE, maxsplit=1)[-1].strip() or "projeto"
        if "estudando " in lowered:
            return re.split(r"estudando\s+", text, flags=re.IGNORECASE, maxsplit=1)[-1].strip() or "com foco"
        aliases = {
            "codando": "no VS Code",
            "programando": "no VS Code",
            "estudando": "com foco",
            "ouvindo musica": "uma playlist",
        }
        return aliases.get(lowered, text[:60])

    def _known_topic(self, prompt: str) -> str:
        text = self._normalize(prompt)
        topics = [
            ("league of legends", "League of Legends"),
            ("league", "League of Legends"),
            ("lol", "League of Legends"),
            ("valorant", "Valorant"),
            ("minecraft", "Minecraft"),
            ("roblox", "Roblox"),
            ("counter strike", "Counter-Strike 2"),
            ("cs2", "Counter-Strike 2"),
            ("steam", "Steam"),
            ("spotify", "Spotify"),
            ("vscode", "VS Code"),
            ("vs code", "VS Code"),
            ("python", "Python"),
            ("node", "Node.js"),
        ]
        for needle, label in topics:
            if needle in text:
                return label
        return ""

    def _polish(self, value: str, intent: Intent, secondary: bool = False) -> str:
        value = value.strip()
        if not value:
            return self._state_for(intent, self._profiles()[intent.mood], None) if secondary else self._details_for(intent, self._profiles()[intent.mood], None)
        if intent.style == "professional":
            prefix = "Foco em" if secondary else "Trabalhando em"
            return self._limit(f"{prefix} {value.lower()}", 80)
        if intent.style == "funny":
            return self._limit(f"{value} | sem prometer estabilidade", 80)
        if intent.style == "cyberpunk":
            return self._limit(f"{value} | modo neon", 80)
        return self._limit(value[0].upper() + value[1:], 80)

    def _normalize(self, value: str) -> str:
        value = value.lower()
        replacements = {"ç": "c", "á": "a", "à": "a", "ã": "a", "â": "a", "é": "e", "ê": "e", "í": "i", "ó": "o", "ô": "o", "õ": "o", "ú": "u"}
        for src, dst in replacements.items():
            value = value.replace(src, dst)
        return value

    def _limit(self, value: Any, max_len: int) -> str:
        text = str(value or "").strip()
        text = re.sub(r"\s+", " ", text)
        return text[:max_len]
