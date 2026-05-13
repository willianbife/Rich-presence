from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class GlassRoot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.wallpaper_path = ""
        self.wallpaper_blur = 26
        self._wallpaper = QPixmap()
        self.setAttribute(Qt.WA_StyledBackground, True)

    def set_wallpaper(self, path: str, blur: int) -> None:
        self.wallpaper_path = path
        self.wallpaper_blur = blur
        self._wallpaper = QPixmap(path) if path else QPixmap()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        if not self._wallpaper.isNull():
            scaled = self._wallpaper.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            if self.wallpaper_blur > 0:
                factor = max(3, min(18, self.wallpaper_blur // 2 + 3))
                blurred_size = QSize(max(1, scaled.width() // factor), max(1, scaled.height() // factor))
                scaled = scaled.scaled(blurred_size, Qt.KeepAspectRatio, Qt.SmoothTransformation).scaled(
                    scaled.size(),
                    Qt.IgnoreAspectRatio,
                    Qt.SmoothTransformation,
                )
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, QColor("#051021"))
            gradient.setColorAt(0.38, QColor("#151038"))
            gradient.setColorAt(0.72, QColor("#062f35"))
            gradient.setColorAt(1.0, QColor("#06070d"))
            painter.fillRect(rect, gradient)

            for color, cx, cy, radius in [
                (QColor(90, 232, 255, 72), 0.17, 0.18, 230),
                (QColor(152, 96, 255, 64), 0.82, 0.18, 260),
                (QColor(77, 255, 159, 52), 0.58, 0.84, 250),
            ]:
                path = QPainterPath()
                path.addEllipse(int(rect.width() * cx - radius), int(rect.height() * cy - radius), radius * 2, radius * 2)
                painter.fillPath(path, color)

        overlay_strength = max(110, min(210, 120 + self.wallpaper_blur * 2))
        painter.fillRect(rect, QColor(2, 4, 12, overlay_strength))
        super().paintEvent(event)


class Card(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(92)
        self.setGraphicsEffect(self._shadow(18, 24))

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 16, 18, 16)
        self.layout.setSpacing(8)

        if title:
            title_label = QLabel(title)
            title_label.setObjectName("SectionTitle")
            self.layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("Muted")
            subtitle_label.setWordWrap(True)
            self.layout.addWidget(subtitle_label)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setGraphicsEffect(self._shadow(30, 42))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setGraphicsEffect(self._shadow(18, 24))
        super().leaveEvent(event)

    @staticmethod
    def _shadow(blur: int, y_offset: int) -> QGraphicsDropShadowEffect:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur)
        shadow.setOffset(0, y_offset)
        shadow.setColor(QColor(0, 0, 0, 115))
        return shadow


class StatCard(QFrame):
    def __init__(self, icon: str, label: str, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("InnerCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        icon_label = QLabel(icon)
        icon_label.setFixedSize(34, 34)
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        value_label = QLabel(value)
        value_label.setObjectName("SectionTitle")
        label_label = QLabel(label)
        label_label.setObjectName("Muted")
        text_box.addWidget(value_label)
        text_box.addWidget(label_label)
        layout.addLayout(text_box)


class StatusBadge(QLabel):
    def __init__(self, text: str = "OFFLINE", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("StatusBadge")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(178, 42)
        self.setProperty("connected", False)
        self._connected = False
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 0)
        self._shadow.setBlurRadius(12)
        self._shadow.setColor(QColor(0, 0, 0, 145))
        self.setGraphicsEffect(self._shadow)

    def set_connected(self, connected: bool) -> None:
        if connected == self._connected and self.text() == ("ONLINE" if connected else "OFFLINE"):
            return
        self._connected = connected
        self.setProperty("connected", connected)
        self.setText("ONLINE" if connected else "OFFLINE")
        self.style().unpolish(self)
        self.style().polish(self)


class AnimatedStackMixin:
    def fade_in_widget(self, widget: QWidget) -> None:
        effect = widget.graphicsEffect()
        if effect is None:
            from PySide6.QtWidgets import QGraphicsOpacityEffect

            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setStartValue(0.2)
        animation.setEndValue(1.0)
        animation.setDuration(220)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start(QPropertyAnimation.DeleteWhenStopped)
