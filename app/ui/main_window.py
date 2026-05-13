from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.models import PresenceButton, PresenceConfig, Preset
from app.core.themes import THEMES, Theme
from app.database.appearance_store import AppearanceStore
from app.database.preset_store import PresetStore
from app.integrations.base import AVAILABLE_INTEGRATIONS
from app.services.automation import SafeAutomationService
from app.services.ai_generator import AIGeneratorService
from app.services.discord_rpc import DiscordRPCService
from app.ui.styles import build_stylesheet
from app.ui.widgets import AnimatedStackMixin, Card, GlassRoot, StatCard, StatusBadge
from app.utils.logger import logger


class AIGeneratorWorker(QObject):
    finished = Signal(object)

    def __init__(self, prompt: str, mode: str, current: PresenceConfig) -> None:
        super().__init__()
        self.prompt = prompt
        self.mode = mode
        self.current = deepcopy(current)

    def run(self) -> None:
        result = AIGeneratorService().generate(self.prompt, self.mode, self.current)
        self.finished.emit(result)


class MainWindow(QMainWindow, AnimatedStackMixin):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Discord Rich Presence Studio")
        self.resize(1220, 780)
        self.setMinimumSize(1040, 680)

        self.appearance_store = AppearanceStore()
        self.appearance = self.appearance_store.load()
        self.theme = THEMES.get(self.appearance.theme_name, THEMES["Aurora Glass"])
        if self.appearance.accent:
            self.theme = Theme(**{**self.theme.__dict__, "accent": self.appearance.accent})
        self.current_config = PresenceConfig()
        self.store = PresetStore()
        self.presets = self.store.load()
        self.rpc = DiscordRPCService()
        self.automation = SafeAutomationService()
        self.automation.configure_presets(self.presets)
        self._last_schedule_minute = ""
        self._last_rpc_payload: dict = {}
        self._rotating_index = 0
        self._ai_thread: QThread | None = None
        self._ai_worker: AIGeneratorWorker | None = None
        self._ai_pending_actions: dict[str, bool | str] = {}

        self.nav_buttons: list[QPushButton] = []
        self.editor_fields: dict[str, QLineEdit] = {}
        self.preview_labels: dict[str, QLabel] = {}

        logger.subscribe(self._append_log)
        self.rpc.status_changed.connect(self._set_connection_status)
        self.automation.preset_selected.connect(self._apply_preset_from_automation)
        self.automation.config_detected.connect(self._apply_detected_config)
        self.schedule_checker = QTimer(self)
        self.schedule_checker.timeout.connect(self._check_schedule)
        self.schedule_checker.start(30_000)
        self.rotation_timer = QTimer(self)
        self.rotation_timer.timeout.connect(self._rotate_presence_phrase)

        self._build_ui()
        self._apply_theme(self.theme)
        self._apply_wallpaper()
        self._load_config_to_editor(self.current_config)
        self._refresh_presets()
        self._refresh_preview()
        logger.log("Aplicativo iniciado. Nenhum token de usuário é usado.", "info")

    def _build_ui(self) -> None:
        root = GlassRoot()
        root.setObjectName("Root")
        self.root = root
        self.setCentralWidget(root)

        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(246)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 22, 18, 18)
        side_layout.setSpacing(10)

        title = QLabel("Presence Studio")
        title.setObjectName("AppTitle")
        side_layout.addWidget(title)

        subtitle = QLabel("RPC visual, seguro e sem token")
        subtitle.setObjectName("Muted")
        side_layout.addWidget(subtitle)
        side_layout.addSpacing(16)

        pages = [
            ("Inicio", "⌂"),
            ("Conexão Discord", "●"),
            ("Editor de Presença", "✎"),
            ("Preview", "◈"),
            ("Presets", "▣"),
            ("Aparência", "◆"),
            ("Integrações", "↔"),
            ("Automação Segura", "◷"),
            ("Logs", "☰"),
        ]

        pages.insert(3, ("IA Generator", "AI"))
        self.stack = QStackedWidget()
        for index, (name, icon) in enumerate(pages):
            button = QPushButton(f"{icon}  {name}")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, i=index: self._switch_page(i))
            self.nav_buttons.append(button)
            side_layout.addWidget(button)

        side_layout.addStretch()
        self.connection_pill = StatusBadge("OFFLINE")
        side_layout.addWidget(self.connection_pill)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack, 1)

        self.stack.addWidget(self._page_home())
        self.stack.addWidget(self._page_connection())
        self.stack.addWidget(self._page_editor())
        self.stack.addWidget(self._page_ai_generator())
        self.stack.addWidget(self._page_preview())
        self.stack.addWidget(self._page_presets())
        self.stack.addWidget(self._page_themes())
        self.stack.addWidget(self._page_integrations())
        self.stack.addWidget(self._page_automation())
        self.stack.addWidget(self._page_logs())

        self._switch_page(0)

    def _page_shell(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(18)
        page_title = QLabel(title)
        page_title.setObjectName("PageTitle")
        layout.addWidget(page_title)
        scroll.setWidget(content)
        return scroll, layout

    def _page_home(self) -> QWidget:
        page, layout = self._page_shell("Discord Rich Presence Studio")

        hero = Card("Dashboard premium", "Painel futurista com status ao vivo, atalhos, presets e aparência personalizável.")
        hero_row = QHBoxLayout()
        hero_row.addWidget(QLabel("Indicador de status"))
        hero_row.addStretch()
        self.top_status_badge = StatusBadge("OFFLINE")
        hero_row.addWidget(self.top_status_badge)
        hero.layout.addLayout(hero_row)
        layout.addWidget(hero)

        stats = QHBoxLayout()
        stats.addWidget(StatCard("RPC", "Integração oficial", "Seguro"))
        stats.addWidget(StatCard("JSON", "Presets locais", str(len(self.presets))))
        stats.addWidget(StatCard("UI", "Preview em tempo real", "Live"))
        layout.addLayout(stats)

        grid = QGridLayout()
        grid.setSpacing(14)
        shortcuts = [
            ("Conectar Discord", "Informe o Client ID da sua aplicação e conecte ao RPC local.", 1),
            ("Editar presença", "Configure textos, imagens, botões e timestamp com feedback imediato.", 2),
            ("Salvar preset", "Guarde configurações prontas para alternar depois.", 5),
            ("Automação segura", "Alterne entre presets sem usar token, selfbot ou ações proibidas.", 8),
        ]
        for position, (title, text, target) in enumerate(shortcuts):
            card = Card(title, text)
            card.mousePressEvent = lambda event, i=target: self._switch_page(i)
            grid.addWidget(card, position // 2, position % 2)
        layout.addLayout(grid)
        layout.addStretch()
        return page

    def _page_connection(self) -> QWidget:
        page, layout = self._page_shell("Conexão Discord")

        card = Card("Client ID da aplicação", "Use o ID público da aplicação criada no Discord Developer Portal.")
        self.client_id_input = QLineEdit()
        self.client_id_input.setPlaceholderText("Ex.: 123456789012345678")
        self.client_id_input.setText("1503888352364204042")
        connect_button = QPushButton("Conectar")
        connect_button.setObjectName("PrimaryButton")
        connect_button.clicked.connect(self._connect_rpc)
        disconnect_button = QPushButton("Desconectar")
        disconnect_button.clicked.connect(self.rpc.disconnect)
        self.connection_status = QLabel("Aguardando conexão.")
        self.connection_status.setObjectName("Muted")

        row = QHBoxLayout()
        row.addWidget(self.client_id_input, 1)
        row.addWidget(connect_button)
        row.addWidget(disconnect_button)
        card.layout.addLayout(row)
        card.layout.addWidget(self.connection_status)
        layout.addWidget(card)

        instructions = Card("Como criar a aplicação", "")
        steps = QLabel(
            "1. Acesse discord.com/developers/applications.\n"
            "2. Crie uma nova aplicação e copie o Application ID.\n"
            "3. Em Rich Presence > Art Assets, envie as imagens e use os nomes dos assets nos campos.\n"
            "4. Abra o Discord desktop antes de conectar.\n"
            "5. Este app usa somente Discord RPC local. Token de usuário nunca é necessário."
        )
        steps.setObjectName("Muted")
        steps.setWordWrap(True)
        instructions.layout.addWidget(steps)
        layout.addWidget(instructions)
        layout.addStretch()
        return page

    def _page_editor(self) -> QWidget:
        page, layout = self._page_shell("Editor de Presença")

        form_card = Card("Configuração visual", "Tudo que você edita aqui atualiza o preview automaticamente.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        fields = [
            ("details", "Nome principal / details"),
            ("state", "Estado / state"),
            ("large_image", "Imagem grande"),
            ("large_text", "Texto da imagem grande"),
            ("small_image", "Imagem pequena"),
            ("small_text", "Texto da imagem pequena"),
        ]
        for row, (key, label) in enumerate(fields):
            grid.addWidget(QLabel(label), row, 0)
            edit = QLineEdit()
            edit.textChanged.connect(self._editor_changed)
            self.editor_fields[key] = edit
            grid.addWidget(edit, row, 1)

        self.timestamp_check = QCheckBox("Usar timestamp de início")
        self.timestamp_check.stateChanged.connect(self._editor_changed)
        grid.addWidget(self.timestamp_check, len(fields), 1)
        form_card.layout.addLayout(grid)

        buttons_card = Card("Botões com links", "O Discord permite até dois botões por presença.")
        self.button_label_1 = QLineEdit()
        self.button_url_1 = QLineEdit()
        self.button_label_2 = QLineEdit()
        self.button_url_2 = QLineEdit()
        for widget, placeholder in [
            (self.button_label_1, "Texto do botão 1"),
            (self.button_url_1, "https://..."),
            (self.button_label_2, "Texto do botão 2"),
            (self.button_url_2, "https://..."),
        ]:
            widget.setPlaceholderText(placeholder)
            widget.textChanged.connect(self._editor_changed)
        button_grid = QGridLayout()
        button_grid.addWidget(self.button_label_1, 0, 0)
        button_grid.addWidget(self.button_url_1, 0, 1)
        button_grid.addWidget(self.button_label_2, 1, 0)
        button_grid.addWidget(self.button_url_2, 1, 1)
        buttons_card.layout.addLayout(button_grid)

        ai_card = Card("IA Generator", "Gere, melhore e crie frases rotativas sem travar a interface.")
        self.ai_prompt = QTextEdit()
        self.ai_prompt.setPlaceholderText("Descreva a vibe: programando de madrugada, estudando redes, jogando Valorant...")
        self.ai_prompt.setMinimumHeight(88)
        self.ai_prompt.setMaximumHeight(130)
        ai_card.layout.addWidget(self.ai_prompt)
        ai_actions = QHBoxLayout()
        for label, mode in [
            ("Gerar com IA", "generate"),
            ("Melhorar presenca atual", "improve"),
            ("Gerar frases rotativas", "phrases"),
        ]:
            button = QPushButton(label)
            if mode == "generate":
                button.setObjectName("PrimaryButton")
            button.clicked.connect(lambda checked=False, m=mode: self._run_ai_generator(m))
            ai_actions.addWidget(button)
        ai_actions.addStretch()
        ai_card.layout.addLayout(ai_actions)
        self.ai_status = QLabel("A IA usa GEMINI_API_KEY quando disponivel e fallback local quando falhar.")
        self.ai_status.setObjectName("Muted")
        self.ai_status.setWordWrap(True)
        ai_card.layout.addWidget(self.ai_status)

        rotate_card = Card("Frases rotativas", "Uma frase por linha. Intervalo minimo de 15 segundos.")
        self.rotating_phrases_edit = QTextEdit()
        self.rotating_phrases_edit.setMinimumHeight(90)
        self.rotating_phrases_edit.setPlaceholderText("Debugando o impossivel\nConstruindo presenca inteligente\nCodando sem travar o PC")
        self.rotating_phrases_edit.textChanged.connect(self._editor_changed)
        self.rotation_seconds = QSpinBox()
        self.rotation_seconds.setRange(15, 3600)
        self.rotation_seconds.setValue(15)
        start_rotation = QPushButton("Ativar frases")
        start_rotation.setObjectName("PrimaryButton")
        start_rotation.clicked.connect(self._start_phrase_rotation)
        stop_rotation = QPushButton("Pausar frases")
        stop_rotation.clicked.connect(self.rotation_timer.stop)
        rotate_row = QHBoxLayout()
        rotate_row.addWidget(QLabel("Intervalo"))
        rotate_row.addWidget(self.rotation_seconds)
        rotate_row.addWidget(QLabel("segundos"))
        rotate_row.addStretch()
        rotate_row.addWidget(start_rotation)
        rotate_row.addWidget(stop_rotation)
        rotate_card.layout.addWidget(self.rotating_phrases_edit)
        rotate_card.layout.addLayout(rotate_row)

        actions = QHBoxLayout()
        send_button = QPushButton("Enviar para Discord")
        send_button.setObjectName("PrimaryButton")
        send_button.clicked.connect(self._send_current_to_rpc)
        save_button = QPushButton("Salvar como preset")
        save_button.clicked.connect(self._save_current_as_preset)
        actions.addWidget(send_button)
        actions.addWidget(save_button)
        actions.addStretch()

        layout.addWidget(form_card)
        layout.addWidget(buttons_card)
        layout.addWidget(ai_card)
        layout.addWidget(rotate_card)
        layout.addLayout(actions)
        layout.addStretch()
        return page

    def _page_ai_generator(self) -> QWidget:
        page, layout = self._page_shell("IA Generator")

        chat_card = Card("Chat de IA para Rich Presence", "Converse com a IA, gere presets e aplique o resultado no editor.")
        self.ai_chat_history = QTextEdit()
        self.ai_chat_history.setReadOnly(True)
        self.ai_chat_history.setMinimumHeight(260)
        self.ai_chat_history.setText(
            "IA: Me diga a vibe da sua presenca. Ex.: 'programando em Python no modo cyberpunk' "
            "ou 'melhore minha presenca atual para algo profissional'."
        )
        self.ai_chat_input = QTextEdit()
        self.ai_chat_input.setPlaceholderText("Digite o pedido para a IA...")
        self.ai_chat_input.setMinimumHeight(90)
        self.ai_chat_input.setMaximumHeight(130)

        chat_actions = QHBoxLayout()
        send = QPushButton("Enviar")
        send.setObjectName("PrimaryButton")
        send.clicked.connect(lambda: self._run_ai_chat("generate"))
        activate = QPushButton("Ativar no Discord")
        activate.clicked.connect(lambda: self._run_ai_chat("activate"))
        improve = QPushButton("Melhorar atual")
        improve.clicked.connect(lambda: self._run_ai_chat("improve"))
        phrases = QPushButton("Frases rotativas")
        phrases.clicked.connect(lambda: self._run_ai_chat("phrases"))
        save = QPushButton("Salvar como preset")
        save.clicked.connect(self._save_current_as_preset)
        chat_actions.addWidget(send)
        chat_actions.addWidget(activate)
        chat_actions.addWidget(improve)
        chat_actions.addWidget(phrases)
        chat_actions.addWidget(save)
        chat_actions.addStretch()

        self.ai_chat_status = QLabel("Configure GEMINI_API_KEY no .env. Se falhar, o gerador local assume.")
        self.ai_chat_status.setObjectName("Muted")
        self.ai_chat_status.setWordWrap(True)
        chat_card.layout.addWidget(self.ai_chat_history)
        chat_card.layout.addWidget(self.ai_chat_input)
        chat_card.layout.addLayout(chat_actions)
        chat_card.layout.addWidget(self.ai_chat_status)
        layout.addWidget(chat_card)

        quick_card = Card("Resultado", "Quando a IA responder, os campos do editor sao preenchidos automaticamente.")
        apply_editor = QPushButton("Ir para o editor")
        apply_editor.clicked.connect(lambda: self._switch_page(2))
        send_discord = QPushButton("Enviar para Discord")
        send_discord.setObjectName("PrimaryButton")
        send_discord.clicked.connect(self._send_current_to_rpc)
        row = QHBoxLayout()
        row.addWidget(apply_editor)
        row.addWidget(send_discord)
        row.addStretch()
        quick_card.layout.addLayout(row)
        layout.addWidget(quick_card)
        layout.addStretch()
        return page

    def _page_preview(self) -> QWidget:
        page, layout = self._page_shell("Preview")
        preview = QFrame()
        preview.setObjectName("PreviewCard")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(20, 18, 20, 18)
        preview_layout.setSpacing(14)

        header = QLabel("Discord Rich Presence Studio")
        header.setObjectName("SectionTitle")
        preview_layout.addWidget(header)

        body = QHBoxLayout()
        self.preview_art = QLabel("IMG")
        self.preview_art.setFixedSize(104, 104)
        self.preview_art.setAlignment(Qt.AlignCenter)
        self.preview_art.setObjectName("InnerCard")
        body.addWidget(self.preview_art)

        text_col = QVBoxLayout()
        for key in ["details", "state", "large_text", "small_text", "timestamp"]:
            label = QLabel("")
            if key != "details":
                label.setObjectName("Muted")
            label.setWordWrap(True)
            self.preview_labels[key] = label
            text_col.addWidget(label)
        body.addLayout(text_col, 1)
        preview_layout.addLayout(body)

        self.preview_buttons = QLabel("")
        self.preview_buttons.setWordWrap(True)
        preview_layout.addWidget(self.preview_buttons)
        layout.addWidget(preview)
        layout.addStretch()
        return page

    def _page_presets(self) -> QWidget:
        page, layout = self._page_shell("Presets")
        self.preset_search = QLineEdit()
        self.preset_search.setPlaceholderText("Pesquisar presets...")
        self.preset_search.textChanged.connect(self._refresh_presets)
        layout.addWidget(self.preset_search)
        content = QHBoxLayout()
        self.preset_list = QListWidget()
        self.preset_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.preset_list.itemDoubleClicked.connect(lambda item: self._load_selected_preset())
        content.addWidget(self.preset_list, 1)

        actions_card = Card("Gerenciar presets", "Dê dois cliques em um preset para aplicar.")
        for label, handler, danger in [
            ("Aplicar", self._load_selected_preset, False),
            ("Favoritar", self._favorite_selected_preset, False),
            ("Renomear", self._rename_selected_preset, False),
            ("Atualizar com editor atual", self._update_selected_preset, False),
            ("Duplicar", self._duplicate_selected_preset, False),
            ("Excluir", self._delete_selected_preset, True),
            ("Importar JSON", self._import_presets, False),
            ("Exportar JSON", self._export_presets, False),
        ]:
            button = QPushButton(label)
            if danger:
                button.setObjectName("DangerButton")
            button.clicked.connect(handler)
            actions_card.layout.addWidget(button)
        content.addWidget(actions_card)
        layout.addLayout(content)
        return page

    def _page_themes(self) -> QWidget:
        page, layout = self._page_shell("Aparência")
        theme_card = Card("Tema e cor", "Troque o visual completo ou ajuste a cor principal.")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.setCurrentText(self.theme.name)
        self.theme_combo.currentTextChanged.connect(lambda name: self._apply_theme(THEMES[name]))

        accent_button = QPushButton("Escolher cor principal")
        accent_button.clicked.connect(self._choose_accent)
        theme_card.layout.addWidget(self.theme_combo)
        theme_card.layout.addWidget(accent_button)
        layout.addWidget(theme_card)

        wallpaper_card = Card("Wallpaper personalizado", "Escolha qualquer imagem local, com blur e overlay escuro para preservar a leitura.")
        choose_wallpaper = QPushButton("Trocar wallpaper")
        choose_wallpaper.setObjectName("PrimaryButton")
        choose_wallpaper.clicked.connect(self._choose_wallpaper)
        remove_wallpaper = QPushButton("Remover wallpaper")
        remove_wallpaper.clicked.connect(self._remove_wallpaper)
        restore_wallpaper = QPushButton("Restaurar padrão")
        restore_wallpaper.clicked.connect(self._restore_default_wallpaper)
        self.wallpaper_label = QLabel(self._wallpaper_label_text())
        self.wallpaper_label.setObjectName("Muted")
        wallpaper_buttons = QHBoxLayout()
        wallpaper_buttons.addWidget(choose_wallpaper)
        wallpaper_buttons.addWidget(remove_wallpaper)
        wallpaper_buttons.addWidget(restore_wallpaper)
        wallpaper_buttons.addStretch()
        wallpaper_card.layout.addLayout(wallpaper_buttons)
        wallpaper_card.layout.addWidget(self.wallpaper_label)
        layout.addWidget(wallpaper_card)

        tuning_card = Card("Vidro e profundidade", "Ajuste o blur do wallpaper e a transparência dos cards.")
        self.blur_slider = QSlider(Qt.Horizontal)
        self.blur_slider.setRange(0, 45)
        self.blur_slider.setValue(self.appearance.blur)
        self.blur_slider.valueChanged.connect(self._appearance_sliders_changed)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(72, 96)
        self.opacity_slider.setValue(max(72, self.appearance.card_opacity))
        self.opacity_slider.valueChanged.connect(self._appearance_sliders_changed)
        tuning_card.layout.addWidget(QLabel("Blur do wallpaper"))
        tuning_card.layout.addWidget(self.blur_slider)
        tuning_card.layout.addWidget(QLabel("Transparência dos cards"))
        tuning_card.layout.addWidget(self.opacity_slider)
        layout.addWidget(tuning_card)
        layout.addStretch()
        return page

    def _page_integrations(self) -> QWidget:
        page, layout = self._page_shell("Integrações")
        grid = QGridLayout()
        grid.setSpacing(14)
        for index, integration in enumerate(AVAILABLE_INTEGRATIONS):
            card = Card(integration.name, integration.description)
            badge = QLabel(f"Status: {integration.status}")
            badge.setObjectName("Muted")
            card.layout.addWidget(badge)
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        layout.addStretch()
        return page

    def _page_automation(self) -> QWidget:
        page, layout = self._page_shell("Automação Segura")
        card = Card("Alternância entre presets", "Automação local e permitida: apenas troca presenças salvas via RPC.")
        self.rotation_minutes = QSpinBox()
        self.rotation_minutes.setRange(1, 240)
        self.rotation_minutes.setValue(15)
        start = QPushButton("Iniciar rotação")
        start.setObjectName("PrimaryButton")
        start.clicked.connect(lambda: self.automation.start_rotation(self.rotation_minutes.value()))
        stop = QPushButton("Pausar rotação")
        stop.clicked.connect(self.automation.stop_rotation)
        self.start_on_launch_check = QCheckBox("Ativar presença atual ao abrir o aplicativo")
        self.start_on_launch_check.stateChanged.connect(self._toggle_start_on_launch)

        row = QHBoxLayout()
        row.addWidget(QLabel("Trocar a cada"))
        row.addWidget(self.rotation_minutes)
        row.addWidget(QLabel("minuto(s)"))
        row.addStretch()
        self.process_detection_check = QCheckBox("Detectar apps abertos: VS Code, Spotify, Chrome, Valorant, Node/Python")
        self.process_detection_check.stateChanged.connect(
            lambda: self.automation.set_process_detection(self.process_detection_check.isChecked(), 15)
        )
        card.layout.addLayout(row)
        card.layout.addWidget(self.start_on_launch_check)
        card.layout.addWidget(self.process_detection_check)
        card.layout.addWidget(start)
        card.layout.addWidget(stop)
        layout.addWidget(card)

        schedule = Card("Ativação por horário", "Estrutura pronta para disparos locais por horário.")
        self.schedule_time = QTimeEdit()
        apply_schedule = QPushButton("Definir horário")
        apply_schedule.clicked.connect(self._set_schedule)
        schedule.layout.addWidget(self.schedule_time)
        schedule.layout.addWidget(apply_schedule)
        layout.addWidget(schedule)
        layout.addStretch()
        return page

    def _page_logs(self) -> QWidget:
        page, layout = self._page_shell("Logs")
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(500)
        layout.addWidget(self.log_box)
        return page

    def _switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.fade_in_widget(self.stack.currentWidget())
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

    def _apply_theme(self, theme: Theme) -> None:
        accent = self.appearance.accent if self.appearance.accent else theme.accent
        self.theme = Theme(**{**theme.__dict__, "accent": accent})
        self.appearance.theme_name = theme.name
        self.appearance.accent = self.theme.accent
        self.appearance_store.save(self.appearance)
        self.setStyleSheet(build_stylesheet(self.theme, self.appearance.card_opacity))
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(self.theme.background))
        palette.setColor(QPalette.WindowText, QColor(self.theme.text))
        self.setPalette(palette)
        self._refresh_preview()

    def _choose_accent(self) -> None:
        color = QColorDialog.getColor(QColor(self.theme.accent), self, "Cor principal")
        if not color.isValid():
            return
        self.appearance.accent = color.name()
        self.theme = Theme(**{**self.theme.__dict__, "accent": color.name()})
        self._apply_theme(self.theme)
        logger.log(f"Cor principal alterada para {color.name()}.", "info")

    def _apply_wallpaper(self) -> None:
        self.root.set_wallpaper(self.appearance.wallpaper_path, self.appearance.blur)
        if hasattr(self, "wallpaper_label"):
            self.wallpaper_label.setText(self._wallpaper_label_text())

    def _choose_wallpaper(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher wallpaper",
            "",
            "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not file_name:
            return
        self.appearance.wallpaper_path = self.appearance_store.import_wallpaper(Path(file_name))
        self.appearance_store.save(self.appearance)
        self._apply_wallpaper()
        logger.log("Wallpaper personalizado aplicado e salvo localmente.", "success")

    def _remove_wallpaper(self) -> None:
        self.appearance.wallpaper_path = ""
        self.appearance_store.save(self.appearance)
        self._apply_wallpaper()
        logger.log("Wallpaper removido. Fundo premium padrão ativo.", "info")

    def _restore_default_wallpaper(self) -> None:
        self.appearance.wallpaper_path = ""
        self.appearance.blur = 26
        self.appearance.card_opacity = 78
        if hasattr(self, "blur_slider"):
            self.blur_slider.blockSignals(True)
            self.blur_slider.setValue(self.appearance.blur)
            self.blur_slider.blockSignals(False)
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(self.appearance.card_opacity)
            self.opacity_slider.blockSignals(False)
        self.appearance_store.save(self.appearance)
        self._apply_wallpaper()
        self._apply_theme(self.theme)
        logger.log("Aparência padrão restaurada.", "info")

    def _appearance_sliders_changed(self) -> None:
        self.appearance.blur = self.blur_slider.value()
        self.appearance.card_opacity = self.opacity_slider.value()
        self.appearance_store.save(self.appearance)
        self._apply_wallpaper()
        self.setStyleSheet(build_stylesheet(self.theme, self.appearance.card_opacity))

    def _wallpaper_label_text(self) -> str:
        return self.appearance.wallpaper_path or "Usando wallpaper padrão dinâmico."

    def _connect_rpc(self) -> bool:
        connected = self.rpc.connect(self.client_id_input.text())
        if connected:
            self._send_current_to_rpc(force=True)
        return connected

    def _set_connection_status(self, message: str, connected: bool) -> None:
        self.connection_status.setText(message)
        self.connection_pill.set_connected(connected)
        if hasattr(self, "top_status_badge"):
            self.top_status_badge.set_connected(connected)

    def _rotating_phrases(self) -> list[str]:
        if not hasattr(self, "rotating_phrases_edit"):
            return self.current_config.rotating_phrases
        return [line.strip() for line in self.rotating_phrases_edit.toPlainText().splitlines() if line.strip()]

    def _send_current_to_rpc(self, force: bool = False) -> bool:
        payload = self.current_config.to_rpc_payload()
        if not force and payload == self._last_rpc_payload:
            logger.log("Presenca nao enviada: nenhum campo mudou.", "info")
            return True
        if self.rpc.update_presence(self.current_config):
            self._last_rpc_payload = payload
            return True
        return False

    def _ensure_rpc_connected(self) -> bool:
        if self.rpc.connected:
            return True
        client_id = self.client_id_input.text().strip()
        if not client_id:
            logger.log("A IA nao conseguiu conectar: informe um Client ID primeiro.", "warning")
            return False
        return self.rpc.connect(client_id)

    def _run_ai_generator(self, mode: str) -> None:
        if self._ai_thread and self._ai_thread.isRunning():
            logger.log("Aguarde a geracao atual terminar.", "warning")
            return
        self.ai_status.setText("Gerando com IA...")
        self.ai_status.repaint()
        prompt = self.ai_prompt.toPlainText()
        self._ai_thread = QThread(self)
        worker = AIGeneratorWorker(prompt, mode, self.current_config)
        self._ai_worker = worker
        worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(worker.run)
        worker.finished.connect(self._apply_ai_result)
        worker.finished.connect(self._ai_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self._ai_thread.finished.connect(self._ai_thread.deleteLater)
        self._ai_thread.finished.connect(lambda: setattr(self, "_ai_worker", None))
        self._ai_thread.start()

    def _run_ai_chat(self, mode: str) -> None:
        prompt = self.ai_chat_input.toPlainText().strip()
        if not prompt and mode == "generate":
            logger.log("Digite uma mensagem para a IA.", "warning")
            return
        self._ai_chat_pending_prompt = prompt or mode
        self._ai_pending_actions = self._infer_ai_actions(prompt, mode)
        extracted_client_id = self._extract_client_id(prompt)
        if extracted_client_id:
            self.client_id_input.setText(extracted_client_id)
            self.ai_chat_history.append(f"\nSistema: Client ID detectado e preenchido: {extracted_client_id}")
        self.ai_chat_history.append(f"\nVoce: {prompt or 'Use a presenca atual.'}")
        self.ai_chat_status.setText("Gerando resposta...")
        self.ai_prompt.setPlainText(prompt)
        self._run_ai_generator(mode)

    def _apply_ai_result(self, config: PresenceConfig) -> None:
        if self._ai_thread:
            self._ai_thread = None
        self._ai_worker = None
        if self.sender() is not None:
            self._load_config_to_editor(config)
        self.ai_status.setText("Resultado aplicado ao editor. Voce pode enviar ou salvar como preset.")
        action_result = ""
        if self._ai_pending_actions.get("send_to_discord"):
            if self._ensure_rpc_connected() and self._send_current_to_rpc(force=True):
                action_result = "\nAcao: conectei/atualizei via Discord RPC. Confira seu perfil no Discord desktop."
            else:
                action_result = "\nAcao: nao consegui enviar. Abra o Discord desktop e confira o Client ID."
        if hasattr(self, "ai_chat_history"):
            phrases = ", ".join(config.rotating_phrases[:3]) if config.rotating_phrases else "sem frases rotativas"
            self.ai_chat_history.append(
                "\nIA: Pronto. Apliquei no editor:\n"
                f"Titulo/details: {config.details}\n"
                f"Estado: {config.state}\n"
                f"Mood: {config.mood}\n"
                f"Frases: {phrases}"
                f"{action_result}"
            )
            status = "Resposta aplicada."
            if self._ai_pending_actions.get("send_to_discord"):
                status += " Tambem tentei ativar no Discord."
            self.ai_chat_status.setText(status)
            self.ai_chat_input.clear()
        self._ai_pending_actions = {}
        logger.log("IA Generator aplicou uma presenca ao editor.", "success")

    def _infer_ai_actions(self, prompt: str, mode: str) -> dict[str, bool | str]:
        text = prompt.lower()
        send_words = [
            "ativ",
            "conect",
            "aparecer",
            "perfil",
            "discord",
            "enviar",
            "manda",
            "coloca no meu perfil",
            "rich presence",
            "presenca agora",
        ]
        should_send = mode == "activate" or any(word in text for word in send_words)
        return {"send_to_discord": should_send}

    def _extract_client_id(self, prompt: str) -> str:
        match = re.search(r"\b\d{17,22}\b", prompt)
        return match.group(0) if match else ""

    def _start_phrase_rotation(self) -> None:
        phrases = self._rotating_phrases()
        if not phrases:
            logger.log("Adicione pelo menos uma frase rotativa.", "warning")
            return
        self.current_config.rotating_phrases = phrases
        self.rotation_timer.start(max(15, self.rotation_seconds.value()) * 1000)
        self._rotate_presence_phrase()
        logger.log("Frases rotativas ativadas com intervalo seguro.", "success")

    def _rotate_presence_phrase(self) -> None:
        phrases = self._rotating_phrases()
        if not phrases:
            self.rotation_timer.stop()
            return
        phrase = phrases[self._rotating_index % len(phrases)]
        self._rotating_index += 1
        if phrase == self.current_config.state:
            return
        self.current_config.state = phrase
        self.editor_fields["state"].blockSignals(True)
        self.editor_fields["state"].setText(phrase)
        self.editor_fields["state"].blockSignals(False)
        self._refresh_preview()
        self._send_current_to_rpc()

    def _editor_changed(self) -> None:
        self.current_config = PresenceConfig(
            details=self.editor_fields["details"].text(),
            state=self.editor_fields["state"].text(),
            large_image=self.editor_fields["large_image"].text(),
            large_text=self.editor_fields["large_text"].text(),
            small_image=self.editor_fields["small_image"].text(),
            small_text=self.editor_fields["small_text"].text(),
            rotating_phrases=self._rotating_phrases(),
            mood=self.current_config.mood,
            buttons=[
                PresenceButton(self.button_label_1.text(), self.button_url_1.text()),
                PresenceButton(self.button_label_2.text(), self.button_url_2.text()),
            ],
            timestamp_enabled=self.timestamp_check.isChecked(),
            start_timestamp=self.current_config.start_timestamp,
        )
        self.current_config.ensure_timestamp()
        self._refresh_preview()

    def _load_config_to_editor(self, config: PresenceConfig) -> None:
        self.current_config = deepcopy(config)
        self.current_config.ensure_timestamp()
        for key, field in self.editor_fields.items():
            field.blockSignals(True)
            field.setText(getattr(self.current_config, key))
            field.blockSignals(False)
        buttons = self.current_config.buttons + [PresenceButton(), PresenceButton()]
        for widget, value in [
            (self.button_label_1, buttons[0].label),
            (self.button_url_1, buttons[0].url),
            (self.button_label_2, buttons[1].label),
            (self.button_url_2, buttons[1].url),
        ]:
            widget.blockSignals(True)
            widget.setText(value)
            widget.blockSignals(False)
        self.timestamp_check.blockSignals(True)
        self.timestamp_check.setChecked(self.current_config.timestamp_enabled)
        self.timestamp_check.blockSignals(False)
        if hasattr(self, "rotating_phrases_edit"):
            self.rotating_phrases_edit.blockSignals(True)
            self.rotating_phrases_edit.setPlainText("\n".join(self.current_config.rotating_phrases))
            self.rotating_phrases_edit.blockSignals(False)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if not hasattr(self, "preview_labels"):
            return
        config = self.current_config
        self.preview_art.setText((config.large_image or "IMG").upper()[:10])
        self.preview_labels["details"].setText(config.details or "Nome principal / details")
        self.preview_labels["state"].setText(config.state or "Estado / state")
        self.preview_labels["large_text"].setText(f"Imagem grande: {config.large_text or config.large_image or 'sem asset'}")
        self.preview_labels["small_text"].setText(f"Imagem pequena: {config.small_text or config.small_image or 'sem asset'}")
        self.preview_labels["timestamp"].setText("Com timestamp ativo" if config.timestamp_enabled else "Sem timestamp")
        valid_buttons = [button.label for button in config.buttons if button.is_valid()]
        self.preview_buttons.setText("  ".join(f"[ {label} ]" for label in valid_buttons))

    def _refresh_presets(self) -> None:
        self.preset_list.clear()
        query = self.preset_search.text().strip().lower() if hasattr(self, "preset_search") else ""
        for preset in self.presets:
            haystack = f"{preset.name} {preset.config.details} {preset.config.state} {preset.config.mood}".lower()
            if query and query not in haystack:
                continue
            prefix = "* " if preset.favorite else ""
            item = QListWidgetItem(f"{prefix}{preset.name}  [{preset.config.mood}]")
            item.setData(Qt.UserRole, preset.id)
            self.preset_list.addItem(item)
        self.automation.configure_presets(self.presets)

    def _selected_preset(self) -> Preset | None:
        item = self.preset_list.currentItem()
        if not item:
            return None
        preset_id = item.data(Qt.UserRole)
        return next((preset for preset in self.presets if preset.id == preset_id), None)

    def _load_selected_preset(self) -> None:
        preset = self._selected_preset()
        if not preset:
            logger.log("Selecione um preset primeiro.", "warning")
            return
        self._load_config_to_editor(preset.config)
        self._send_current_to_rpc()
        logger.log(f"Preset aplicado: {preset.name}.", "success")

    def _save_current_as_preset(self) -> None:
        name = f"Preset {len(self.presets) + 1}"
        self.presets.append(Preset(name=name, config=deepcopy(self.current_config)))
        self.store.save(self.presets)
        self._refresh_presets()
        logger.log(f"Preset salvo: {name}.", "success")

    def _update_selected_preset(self) -> None:
        preset = self._selected_preset()
        if not preset:
            logger.log("Selecione um preset para atualizar.", "warning")
            return
        preset.config = deepcopy(self.current_config)
        self.store.save(self.presets)
        logger.log(f"Preset atualizado: {preset.name}.", "success")

    def _duplicate_selected_preset(self) -> None:
        preset = self._selected_preset()
        if not preset:
            logger.log("Selecione um preset para duplicar.", "warning")
            return
        self.presets.append(Preset(name=f"{preset.name} cópia", config=deepcopy(preset.config)))
        self.store.save(self.presets)
        self._refresh_presets()
        logger.log(f"Preset duplicado: {preset.name}.", "success")

    def _favorite_selected_preset(self) -> None:
        preset = self._selected_preset()
        if not preset:
            logger.log("Selecione um preset para favoritar.", "warning")
            return
        preset.favorite = not preset.favorite
        self.presets.sort(key=lambda item: (not item.favorite, item.name.lower()))
        self.store.save(self.presets)
        self._refresh_presets()
        logger.log(f"Favorito atualizado: {preset.name}.", "success")

    def _rename_selected_preset(self) -> None:
        preset = self._selected_preset()
        if not preset:
            logger.log("Selecione um preset para renomear.", "warning")
            return
        name, ok = QInputDialog.getText(self, "Renomear preset", "Nome do preset:", text=preset.name)
        if not ok or not name.strip():
            return
        preset.name = name.strip()
        self.store.save(self.presets)
        self._refresh_presets()
        logger.log(f"Preset renomeado para: {preset.name}.", "success")

    def _delete_selected_preset(self) -> None:
        preset = self._selected_preset()
        if not preset:
            logger.log("Selecione um preset para excluir.", "warning")
            return
        self.presets = [item for item in self.presets if item.id != preset.id]
        self.store.save(self.presets)
        self._refresh_presets()
        logger.log(f"Preset excluído: {preset.name}.", "info")

    def _import_presets(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "Importar presets", "", "JSON (*.json)")
        if not file_name:
            return
        try:
            imported = self.store.import_from(Path(file_name))
            self.presets.extend(imported)
            self.store.save(self.presets)
            self._refresh_presets()
            logger.log(f"{len(imported)} preset(s) importado(s).", "success")
        except Exception as exc:
            QMessageBox.warning(self, "Importação falhou", str(exc))
            logger.log(f"Erro ao importar presets: {exc}", "error")

    def _export_presets(self) -> None:
        file_name, _ = QFileDialog.getSaveFileName(self, "Exportar presets", "presets.json", "JSON (*.json)")
        if not file_name:
            return
        self.store.export_to(Path(file_name), self.presets)
        logger.log("Presets exportados com sucesso.", "success")

    def _toggle_start_on_launch(self) -> None:
        self.automation.start_on_launch = self.start_on_launch_check.isChecked()
        state = "ativada" if self.automation.start_on_launch else "desativada"
        logger.log(f"Presença ao iniciar {state}.", "info")

    def _set_schedule(self) -> None:
        value = self.schedule_time.time()
        self.automation.set_schedule(value.hour(), value.minute())

    def _apply_preset_from_automation(self, preset: Preset) -> None:
        self._load_config_to_editor(preset.config)
        self._send_current_to_rpc()

    def _apply_detected_config(self, config: PresenceConfig, source: str) -> None:
        self._load_config_to_editor(config)
        self._send_current_to_rpc()
        logger.log(f"Presenca aplicada pela deteccao: {source}.", "info")

    def _check_schedule(self) -> None:
        if not self.automation.should_activate_now():
            return
        marker = self.schedule_time.time().toString("HH:mm")
        if marker == self._last_schedule_minute:
            return
        self._last_schedule_minute = marker
        logger.log("Horário programado alcançado. Aplicando presença atual.", "info")
        self._send_current_to_rpc()

    def _append_log(self, entry: str, level: str) -> None:
        if not hasattr(self, "log_box"):
            QTimer.singleShot(100, lambda: self._append_log(entry, level))
            return
        colors = {
            "success": self.theme.success,
            "warning": self.theme.warning,
            "error": self.theme.danger,
            "info": self.theme.muted,
        }
        color = colors.get(level, self.theme.muted)
        self.log_box.append(f'<span style="color:{color}">{entry}</span>')
