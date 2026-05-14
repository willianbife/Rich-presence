from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from app.core.models import PresenceButton, PresenceConfig
from app.utils.logger import logger


GEMINI_MODEL_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent?key={api_key}"
)


@dataclass(frozen=True)
class ParsedRequest:
    request: str
    subject: str
    mood: str
    style: str
    action: str
    memory: list[dict[str, str]] = field(default_factory=list)


class AIGeneratorService:
    def generate(self, prompt: str, mode: str = "generate", current: PresenceConfig | None = None) -> PresenceConfig:
        envelope = self._read_envelope(prompt)
        request = envelope.get("request", prompt).strip()
        memory = envelope.get("memory", [])
        if not request and current is None:
            return self._fallback("presenca criativa para Discord", "cyberpunk", mode, current, memory)

        api_key = self._api_key()
        if not api_key:
            logger.log("GEMINI_API_KEY ausente. Usando interpretador local.", "warning")
            return self._fallback(request or current.details, current.mood if current else "cyberpunk", mode, current, memory)

        try:
            raw = self._call_gemini(api_key, request, mode, current, memory)
            data = self._extract_json(raw)
            return self._config_from_ai(data, current)
        except urllib.error.HTTPError as exc:
            if exc.code in {403, 429}:
                logger.log("Gemini recusou ou limitou a chamada. Usando interpretador local.", "warning")
            else:
                logger.log(f"Falha HTTP na Gemini ({exc.code}). Usando interpretador local.", "warning")
        except Exception as exc:
            logger.log(f"IA retornou algo invalido ({exc}). Usando interpretador local.", "warning")

        return self._fallback(request or (current.details if current else ""), current.mood if current else "cyberpunk", mode, current, memory)

    def _read_envelope(self, prompt: str) -> dict[str, Any]:
        try:
            data = json.loads(prompt)
        except (TypeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

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

    def _call_gemini(
        self,
        api_key: str,
        prompt: str,
        mode: str,
        current: PresenceConfig | None,
        memory: list[dict[str, str]],
    ) -> str:
        system = """
Voce e um assistente especializado em Discord Rich Presence.
Responda somente JSON valido. Nao use markdown.

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
  "buttons": [{"label": "Texto", "url": "https://example.com/"}],
  "mood": "dev|study|gaming|music|professional|cyberpunk|dark|funny"
}

Regras:
- Entenda o pedido, nao copie a frase do usuario.
- Separe comando, assunto e tom. Exemplo: "ative a rich presence e coloque que a Brenda e farmada, mas engracado" significa assunto "Brenda farmada" com tom funny.
- Se o usuario pedir para ativar/conectar/aparecer no perfil, gere a melhor presenca; o app executa RPC.
- Rich Presence precisa ser curta, natural, legivel no Discord e nao passar de 80 caracteres por linha.
- Use memoria recente quando o pedido for "deixa mais engracado", "melhora isso", "troca so o estado".
- Se o usuario pedir tom burro/imbecil/zoado, use humor, mas nao ofenda pessoas reais de forma pesada.
""".strip()
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "mode": mode,
                                    "user_request": prompt,
                                    "current_presence": current.to_dict() if current else {},
                                    "recent_memory": memory[-6:],
                                },
                                ensure_ascii=False,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
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
                buttons.append(PresenceButton(self._limit(item.get("label", ""), 32), str(item.get("url", ""))))
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
            rotating_phrases=[self._limit(item, 80) for item in phrases if str(item).strip()][:8],
            buttons=buttons[:2],
            mood=self._limit(data.get("mood", "cyberpunk"), 32),
        )

    def _fallback(
        self,
        prompt: str,
        mood: str,
        mode: str,
        current: PresenceConfig | None,
        memory: list[dict[str, str]],
    ) -> PresenceConfig:
        parsed = self._parse_request(prompt, mood, mode, current, memory)
        base = self._profiles()[parsed.mood]

        details = self._details(parsed, current)
        state = self._state(parsed, current)
        phrases = self._phrases(parsed)

        if mode == "phrases" and current:
            details = current.details or details
            state = current.state or state
        if parsed.action == "improve" and current:
            details = self._improve_line(current.details or details, parsed, primary=True)
            state = self._improve_line(current.state or state, parsed, primary=False)

        return PresenceConfig(
            details=details,
            state=state,
            large_image=base["large_image"],
            large_text=base["large_text"],
            small_image="studio_small",
            small_text="Online no Presence Studio",
            rotating_phrases=phrases,
            buttons=self._buttons(parsed),
            mood=parsed.mood,
        )

    def _parse_request(
        self,
        prompt: str,
        default_mood: str,
        mode: str,
        current: PresenceConfig | None,
        memory: list[dict[str, str]],
    ) -> ParsedRequest:
        normalized = self._normalize(prompt)
        remembered_subject = self._last_subject(memory) or (current.details if current else "")
        subject = self._extract_subject(prompt) or remembered_subject
        if self._normalize(subject) in {"isso", "isto", "essa", "esse", "atual", "deixa isso", "melhora isso"}:
            subject = remembered_subject
        mood = self._detect_mood(normalized, default_mood, current, subject)
        style = self._detect_style(normalized)

        if mode == "phrases":
            action = "phrases"
        elif mode == "improve" or any(word in normalized for word in ["melhor", "aprimora", "refina", "mais bonito", "menos generico"]):
            action = "improve"
        elif any(word in normalized for word in ["descricao", "details", "linha principal"]):
            action = "details"
        elif any(word in normalized for word in ["estado", "status", "state", "linha secundaria"]):
            action = "state"
        else:
            action = "generate"

        return ParsedRequest(
            request=prompt,
            subject=self._clean_subject(subject),
            mood=mood,
            style=style,
            action=action,
            memory=memory[-6:] if isinstance(memory, list) else [],
        )

    def _profiles(self) -> dict[str, dict[str, str]]:
        return {
            "dev": {"large_image": "code", "large_text": "Ambiente dev ativo"},
            "study": {"large_image": "study", "large_text": "Modo estudo"},
            "gaming": {"large_image": "game", "large_text": "Modo gamer"},
            "music": {"large_image": "music", "large_text": "Som ambiente"},
            "professional": {"large_image": "work", "large_text": "Modo profissional"},
            "cyberpunk": {"large_image": "cyber", "large_text": "Modo neon"},
            "dark": {"large_image": "dark", "large_text": "Dark workspace"},
            "funny": {"large_image": "meme", "large_text": "Modo shitpost"},
        }

    def _detect_mood(self, text: str, default_mood: str, current: PresenceConfig | None, subject: str) -> str:
        haystack = f"{text} {self._normalize(subject)}"
        scores = {
            "dev": ["cod", "program", "python", "node", "api", "debug", "github", "vscode", "backend", "frontend"],
            "study": ["estud", "aula", "prova", "faculdade", "pesquisa", "curso", "aprend"],
            "gaming": ["jog", "game", "league of legends", "lol", "valorant", "minecraft", "steam", "ranked", "partida", "fps"],
            "music": ["musica", "spotify", "playlist", "ouvindo", "album"],
            "professional": ["profissional", "formal", "trabalho", "cliente", "reuniao", "projeto", "produtiv"],
            "dark": ["dark", "sombrio", "minimal", "preto"],
            "cyberpunk": ["cyber", "neon", "futur", "hacker"],
            "funny": ["meme", "shitpost", "engrac", "hilario", "zoeira", "imbecil", "tosco", "zoado", "burro"],
        }
        mood = "cyberpunk"
        best = 0
        for candidate, words in scores.items():
            score = sum(1 for word in words if word in haystack)
            if score > best:
                best = score
                mood = candidate
        funny_formal = any(word in haystack for word in ["engrac", "hilario", "meme", "zoeira"]) and any(
            word in haystack for word in ["formal", "profissional", "serio"]
        )
        domain_words = scores["dev"] + scores["study"] + scores["gaming"] + scores["music"]
        if funny_formal and not any(word in haystack for word in domain_words):
            mood = "funny"
        if any(word in haystack for word in ["fofo", "fofa", "fofinha", "fofuxa", "cute", "carinho", "meigo"]) and not any(
            word in haystack for word in domain_words
        ):
            mood = "funny"
        if best == 0 and self._is_contextual_request(text):
            mood = current.mood if current and current.mood else (default_mood or "cyberpunk")
        if mood == "funny" and any(word in haystack for word in scores["gaming"]):
            return "gaming"
        return mood if mood in self._profiles() else "cyberpunk"

    def _detect_style(self, text: str) -> str:
        wants_funny = any(word in text for word in ["engrac", "hilario", "meme", "shitpost", "zoeira", "imbecil", "idiota", "tosco", "zoado", "burro"])
        wants_formal = any(word in text for word in ["profissional", "formal", "serio", "clean", "limpo"])
        wants_cute = any(word in text for word in ["fofo", "fofa", "fofinha", "fofuxa", "cute", "carinho", "meigo", "meiga"])
        wants_conceptual = any(word in text for word in ["conceitual", "conceito", "poetico", "poetica", "estetico", "estetica"])
        if wants_cute and wants_conceptual:
            return "cute_conceptual"
        if wants_cute:
            return "cute"
        if wants_conceptual:
            return "conceptual"
        if wants_funny and wants_formal:
            return "formal_funny"
        if wants_funny:
            return "funny"
        if wants_formal:
            return "professional"
        if any(word in text for word in ["dark", "sombrio", "minimal"]):
            return "dark"
        if any(word in text for word in ["cyber", "neon", "futur"]):
            return "cyberpunk"
        return "clean"

    def _is_contextual_request(self, text: str) -> bool:
        return any(word in text for word in ["isso", "isto", "essa", "esse", "atual", "melhora", "refina", "troca so"])

    def _extract_subject(self, prompt: str) -> str:
        known = self._known_subject(prompt)
        if known:
            return known

        text = prompt.strip()
        text = self._strip_tail_instructions(text)
        normalized_text = self._normalize(text)

        transform_match = re.search(
            r"(?:transforme|transforma|deixe|deixa|torne|torna)\s+(?:a\s+)?(?:rich\s*)?(?:presence|presenca|presensce)?\s*(.+?)\s+em\s+algo",
            normalized_text,
            flags=re.IGNORECASE,
        )
        if transform_match:
            return transform_match.group(1).strip()

        claim_match = re.search(
            r"(?:fale|fala|diga|mostre|coloque|coloca|bote|bota|falando)\s+que\s+(.+)",
            normalized_text,
            flags=re.IGNORECASE,
        )
        if claim_match:
            return claim_match.group(1)

        patterns = [
            r"(?:codando|programando)\s+(.+)",
            r"(?:falando|fale|fala)\s+(?:que\s+)?(.+)",
            r"(?:coloque|coloca|bote|bota|diga|mostre)\s+(?:que\s+)?(.+)",
            r"(?:estou|to|tô|tou)\s+(.+)",
            r"(?:sobre|pra|para)\s+(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized_text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return normalized_text

    def _strip_tail_instructions(self, value: str) -> str:
        tails = [
            " porem ",
            " mas ",
            " so que ",
            " mais engracado",
            " mais fofo",
            " mais fofa",
            " modo mais fofo",
            " de um modo ",
            " de uma forma ",
            " de forma ",
            " soq ",
            " do que a forma",
        ]
        text = self._normalize(value)
        for pattern in tails:
            index = text.find(pattern)
            if index >= 0:
                text = text[:index]
        text = text.strip(" ,.-")
        return text

    def _clean_subject(self, subject: str) -> str:
        text = subject.strip()
        text = self._normalize(text)
        known = {
            "league of legends": "League of Legends",
            "valorant": "Valorant",
            "minecraft": "Minecraft",
            "roblox": "Roblox",
            "steam": "Steam",
            "spotify": "Spotify",
            "python": "Python",
            "node.js": "Node.js",
            "vs code": "VS Code",
        }
        if text in known:
            return known[text]
        text = re.sub(r"\b(ative|ativar|conecte|conectar|rich\s*presensce|rich\s*presence|rich\s*presenca|presenca|discord|perfil)\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(coloque|coloca|bote|bota|diga|mostre|fale|fala|falando|transforme|transforma|deixe|deixa|melhora|isso|isto|que|eu|estou|to|tou|tô|sendo|uma|um|a|o)\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(fofinha|fofuxa|fofo|fofa|cute|carinho|meigo|meiga|conceitual|conceito|modo|forma|soq|de)\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip(" ,.-")
        match = re.match(r"(.+?)\s+(?:e|eh|esta|ta)\s+(.+)", text)
        if match:
            left = self._title_case(match.group(1))
            right = match.group(2).strip()
            if any(word in right for word in ["fofinha", "fofuxa", "fofo", "fofa", "cute", "carinho", "meigo", "meiga"]):
                return left
            return f"{left} {right}".strip()
        return self._title_case(text) if len(text) <= 26 else text[:60]

    def _known_subject(self, prompt: str) -> str:
        text = self._normalize(prompt)
        topics = [
            ("league of legends", "League of Legends"),
            ("league", "League of Legends"),
            ("lol", "League of Legends"),
            ("valorant", "Valorant"),
            ("minecraft", "Minecraft"),
            ("roblox", "Roblox"),
            ("steam", "Steam"),
            ("spotify", "Spotify"),
            ("python", "Python"),
            ("node", "Node.js"),
            ("vscode", "VS Code"),
            ("vs code", "VS Code"),
        ]
        for needle, label in topics:
            if needle in text:
                return label
        return ""

    def _last_subject(self, memory: list[dict[str, str]]) -> str:
        if not isinstance(memory, list):
            return ""
        for item in reversed(memory):
            if isinstance(item, dict):
                value = item.get("details") or item.get("subject") or ""
                if value:
                    return value
        return ""

    def _details(self, parsed: ParsedRequest, current: PresenceConfig | None) -> str:
        if parsed.action == "state" and current and current.details:
            return current.details
        subject = parsed.subject
        funny = parsed.style == "funny"

        if parsed.style in {"cute", "cute_conceptual"}:
            return self._limit(self._cute_detail(subject, conceptual=parsed.style == "cute_conceptual"), 80)
        if parsed.style == "conceptual":
            return self._limit(f"{subject} em conceito aberto" if subject else "Presenca em conceito aberto", 80)
        if parsed.mood == "funny":
            if parsed.style in {"professional", "formal_funny"}:
                return self._limit(f"{subject} em comunicado oficial" if subject else "Comunicado oficial do caos", 80)
            return self._limit(f"{subject} virou evento oficial" if subject else "Compilando caos", 80)
        if parsed.mood == "gaming":
            if funny:
                return self._limit(self._funny_gaming_detail(subject), 80)
            return self._limit(f"Jogando {subject}" if subject else "Partida em andamento", 80)
        if parsed.mood == "dev":
            return self._limit(f"Codando {subject}" if subject else "Codando no modo foco", 80)
        if parsed.mood == "study":
            return self._limit(f"Estudando {subject}" if subject else "Estudando com foco", 80)
        if parsed.mood == "music":
            return self._limit(f"Ouvindo {subject}" if subject else "Ouvindo musica", 80)
        if parsed.mood == "professional":
            return self._limit(f"Trabalhando em {subject}" if subject else "Trabalhando em projeto", 80)
        if parsed.mood == "dark":
            return self._limit(subject or "Modo dark ativado", 80)
        if parsed.mood == "cyberpunk":
            return self._limit(subject or "Cyber Terminal", 80)
        return self._limit(subject or "Presence Studio", 80)

    def _state(self, parsed: ParsedRequest, current: PresenceConfig | None) -> str:
        if parsed.action == "details" and current and current.state:
            return current.state
        subject = parsed.subject
        if parsed.style == "cute":
            return "Carinho aplicado ao status"
        if parsed.style == "cute_conceptual":
            return "Ternura em forma de conceito"
        if parsed.style == "conceptual":
            return "Ideia em exibicao"
        if parsed.mood == "funny" and parsed.style in {"professional", "formal_funny"}:
            return "Formalmente sem condicoes"
        if parsed.mood == "gaming" and parsed.style == "funny":
            return "Humor duvidoso, farm garantido"
        states = {
            "gaming": "Partida em andamento",
            "dev": "Debug | Build | Commit",
            "study": "Foco total | Aprendizado",
            "music": "Playlist ligada | Vibe boa",
            "professional": "Planejamento | Execucao",
            "cyberpunk": "Neon | IA | Discord RPC",
            "dark": "Foco silencioso | Dark mode",
            "funny": "Zero contexto, muita conviccao",
        }
        if subject and parsed.style == "professional":
            return self._limit(f"Organizando {subject.lower()}", 80)
        return states.get(parsed.mood, "Online no Presence Studio")

    def _funny_gaming_detail(self, subject: str) -> str:
        normalized = self._normalize(subject)
        if "brenda" in normalized and "farm" in normalized:
            return "Brenda farmou ate o Discord"
        if "league of legends" in normalized:
            return "Perdendo PDL no LoL"
        if "valorant" in normalized:
            return "Errando pixel no Valorant"
        if "minecraft" in normalized:
            return "Minerando com zero plano"
        if subject:
            return f"{subject} em modo absurdo"
        return "Jogando como se fosse estrategia"

    def _cute_detail(self, subject: str, conceptual: bool = False) -> str:
        name = self._primary_name(subject) or "Essa energia"
        if conceptual:
            return f"{name}, conceito de ternura"
        return f"{name} em modo carinho"

    def _phrases(self, parsed: ParsedRequest) -> list[str]:
        subject = parsed.subject or "o momento"
        if parsed.style in {"cute", "cute_conceptual"}:
            name = self._primary_name(subject) or subject
            phrases = [
                f"{name} com aura de abraço",
                "Fofura calibrada no maximo",
                "Modo carinho ativado",
                "Status macio e brilhando",
            ]
            if parsed.style == "cute_conceptual":
                phrases = [
                    f"{name} como ideia bonita",
                    "Ternura em formato abstrato",
                    "Conceito: carinho aplicado",
                    "Um manifesto pequeno de fofura",
                ]
        elif parsed.style == "conceptual":
            phrases = [
                f"{subject} em leitura conceitual",
                "Ideia virando status",
                "Estetica antes da explicacao",
                "Presenca como pequena tese",
            ]
        elif parsed.mood == "funny" and parsed.style in {"professional", "formal_funny"}:
            phrases = [
                f"{subject} em ata oficial",
                "Comunicado serio sobre bobagem",
                "Formalidade com zero estabilidade",
                "Departamento de caos informa",
            ]
        elif parsed.mood == "gaming" and parsed.style == "funny":
            if "brenda" in self._normalize(subject):
                phrases = [
                    "Brenda farmada, bot lane traumatizada",
                    "O minion viu e pediu pausa",
                    "Carry moral em andamento",
                    "Reportaram o senso de humor",
                ]
            else:
                phrases = [
                    f"Sofrendo em {subject}",
                    "Culpando o matchmaking",
                    "Prometi jogar serio",
                    "GG moral em andamento",
                ]
        else:
            bank = {
                "dev": [f"Construindo {subject}", "Debugando sem panico", "So mais um commit", "Build quase verde"],
                "study": [f"Revisando {subject}", "Foco antes da recompensa", "Mais uma pagina vencida", "Aprendizado em andamento"],
                "gaming": [f"Jogando {subject}", "Fila puxada", "Partida em andamento", "Modo clutch ativado"],
                "music": [f"Ouvindo {subject}", "Playlist no ponto", "Volume mental ajustado", "Vibe em loop"],
                "professional": [f"Organizando {subject}", "Modo produtividade", "Prioridades alinhadas", "Entrega em construcao"],
                "cyberpunk": ["Neon ligado", "Terminal respirando", "IA no painel", "Cidade acordada"],
                "dark": ["Foco no escuro", "Minimal e direto", "Silencio produtivo", "Dark mode permanente"],
                "funny": [f"{subject} virou lore", "Caos com estilo", "Zero bugs na imaginacao", "Deploy da bagunca"],
            }
            phrases = bank.get(parsed.mood, [subject, "Online no Presence Studio"])
        return [self._limit(item, 80) for item in phrases[:6]]

    def _improve_line(self, value: str, parsed: ParsedRequest, primary: bool) -> str:
        value = value.strip()
        if not value:
            return self._details(parsed, None) if primary else self._state(parsed, None)
        if parsed.style == "funny":
            return self._limit(f"{value} | agora com lore", 80)
        if parsed.style == "professional":
            return self._limit(f"{'Foco em' if primary else 'Execucao de'} {value.lower()}", 80)
        if parsed.style == "cyberpunk":
            return self._limit(f"{value} | modo neon", 80)
        return self._limit(value[0].upper() + value[1:], 80)

    def _buttons(self, parsed: ParsedRequest) -> list[PresenceButton]:
        if parsed.mood == "dev":
            return [PresenceButton("GitHub", "https://github.com/"), PresenceButton("Projeto", "https://example.com/")]
        return [PresenceButton(), PresenceButton()]

    def _primary_name(self, subject: str) -> str:
        text = self._clean_subject(subject)
        text = re.sub(r"\b(e|eh|esta|ta)\b.*$", "", self._normalize(text)).strip()
        return self._title_case(text)

    def _title_case(self, value: str) -> str:
        small = {"de", "da", "do", "das", "dos", "e", "em", "no", "na"}
        words = []
        for index, word in enumerate(value.split()):
            lowered = word.lower()
            words.append(lowered if index and lowered in small else lowered.capitalize())
        return " ".join(words)

    def _normalize(self, value: str) -> str:
        value = str(value or "").lower()
        normalized = unicodedata.normalize("NFKD", value)
        return "".join(char for char in normalized if not unicodedata.combining(char))

    def _limit(self, value: Any, max_len: int) -> str:
        text = str(value or "").strip()
        text = re.sub(r"\s+", " ", text)
        return text[:max_len]
