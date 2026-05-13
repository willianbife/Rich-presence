from __future__ import annotations

from app.core.themes import Theme


def build_stylesheet(theme: Theme, card_opacity: int = 62) -> str:
    alpha = max(72, min(96, card_opacity)) / 100
    card_bg = f"rgba(13, 18, 34, {alpha:.2f})"
    card_alt = f"rgba(23, 31, 54, {min(0.98, alpha + 0.08):.2f})"
    return f"""
    * {{
        font-family: "Segoe UI", "Inter", Arial, sans-serif;
        font-size: 14px;
        color: {theme.text};
    }}

    QMainWindow, QWidget#Root {{
        background: transparent;
    }}

    QFrame#Sidebar {{
        background: rgba(7, 11, 24, 0.90);
        border-right: 1px solid rgba(142, 247, 255, 0.16);
    }}

    QLabel#AppTitle {{
        font-size: 20px;
        font-weight: 800;
        color: #ffffff;
    }}

    QLabel#PageTitle {{
        font-size: 30px;
        font-weight: 800;
        color: #ffffff;
    }}

    QLabel#SectionTitle {{
        font-size: 17px;
        font-weight: 750;
    }}

    QLabel#Muted {{
        color: {theme.muted};
    }}

    QFrame#Card, QFrame#PreviewCard {{
        background: {card_bg};
        border: 1px solid {theme.border};
        border-radius: 8px;
    }}

    QFrame#InnerCard, QLabel#InnerCard {{
        background: {card_alt};
        border: 1px solid {theme.border};
        border-radius: 8px;
    }}

    QPushButton {{
        background: rgba(25, 34, 58, 0.92);
        border: 1px solid {theme.border};
        border-radius: 8px;
        padding: 11px 16px;
        font-weight: 650;
        min-height: 18px;
    }}

    QPushButton:hover {{
        border-color: {theme.accent};
        background: rgba(48, 66, 112, 0.86);
        color: #ffffff;
    }}

    QPushButton:pressed {{
        background: rgba(15, 21, 36, 0.95);
    }}

    QPushButton:checked, QPushButton#PrimaryButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {theme.accent}, stop:1 {theme.accent_alt});
        color: #071016;
        border-color: {theme.accent};
    }}

    QPushButton#DangerButton {{
        background: {theme.danger};
        color: #ffffff;
        border-color: {theme.danger};
    }}

    QLineEdit, QTextEdit, QSpinBox, QTimeEdit, QComboBox {{
        background: rgba(6, 10, 22, 0.88);
        border: 1px solid {theme.border};
        border-radius: 8px;
        padding: 10px 12px;
        selection-background-color: {theme.accent};
    }}

    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QTimeEdit:focus, QComboBox:focus {{
        border-color: {theme.accent};
    }}

    QCheckBox {{
        spacing: 8px;
    }}

    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 7px;
        border: 1px solid {theme.border};
        background: rgba(7, 11, 24, 0.74);
    }}

    QCheckBox::indicator:checked {{
        background: {theme.success};
        border-color: {theme.success};
    }}

    QSlider::groove:horizontal {{
        height: 8px;
        border-radius: 4px;
        background: rgba(255, 255, 255, 0.12);
    }}

    QSlider::sub-page:horizontal {{
        border-radius: 4px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {theme.accent_alt}, stop:1 {theme.accent});
    }}

    QSlider::handle:horizontal {{
        width: 22px;
        height: 22px;
        margin: -8px 0;
        border-radius: 11px;
        background: #ffffff;
        border: 2px solid {theme.accent};
    }}

    QListWidget {{
        background: {card_bg};
        border: 1px solid {theme.border};
        border-radius: 8px;
        padding: 6px;
    }}

    QListWidget::item {{
        padding: 10px;
        border-radius: 6px;
    }}

    QListWidget::item:selected {{
        background: {theme.accent};
        color: #071016;
    }}

    QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}

    QScrollBar:vertical {{
        background: rgba(7, 11, 24, 0.36);
        width: 10px;
    }}


    QScrollBar::handle:vertical {{
        background: rgba(142, 247, 255, 0.48);
        border-radius: 5px;
    }}

    QTextEdit {{
        font-family: "Cascadia Mono", "Consolas", monospace;
        color: #bfffea;
    }}

    QLabel#StatusBadge {{
        border-radius: 8px;
        padding: 0px;
        font-weight: 900;
        letter-spacing: 0px;
        background: rgba(255, 95, 126, 0.20);
        border: 1px solid rgba(255, 95, 126, 0.46);
        color: #ffc1cb;
    }}

    QLabel#StatusBadge[connected="true"] {{
        background: rgba(77, 255, 159, 0.20);
        border: 1px solid rgba(77, 255, 159, 0.58);
        color: {theme.success};
    }}
    """
