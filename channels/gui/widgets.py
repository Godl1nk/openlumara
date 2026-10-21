# -- AI GENERATED CODE (qwen3.8-flash-next) :: (2026-10-21) harness:openlumara
"""small shared pieces of the qt6 chat UI: content flattening, the chat view
that routes collapsible-header clicks to the window, and the two-line sidebar row"""
import PySide6.QtCore as QtCore
import PySide6.QtGui as QtGui
import PySide6.QtWidgets as QtWidgets


def extract_text(content):
    """flatten chat message content (str or multimodal list) into plain text"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "\n".join(parts)
    return str(content)


class ChatTextEdit(QtWidgets.QTextEdit):
    """text edit that routes clicks on collapsible headers to the window"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        # needed to get move events without a button being held down
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._hand = False

    def _over_header(self, event):
        try:
            pos = self.cursorForPosition(event.position().toPoint()).position()
            return self._window.collapsible_at(pos) is not None
        except Exception:
            return False

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            try:
                pos = self.cursorForPosition(event.position().toPoint()).position()
                if self._window.handle_chat_click(pos):
                    event.accept()
                    return
            except Exception:
                pass
        super().mousePressEvent(event)

    def _show_hand(self, want):
        # only touch the cursor when it actually changes, and unset it outside
        # the headers so text selection keeps its normal pointing
        if want == self._hand:
            return
        self._hand = want
        if want:
            self.viewport().setCursor(QtCore.Qt.PointingHandCursor)
        else:
            self.viewport().unsetCursor()

    def mouseMoveEvent(self, event):
        # pointy hand while hovering a Thoughts header
        self._show_hand(self._over_header(event))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._show_hand(False)
        super().leaveEvent(event)


class ChatListRow(QtWidgets.QWidget):
    """two-line sidebar row: title + date modified"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        # a little air between the title line and the date line
        layout.setSpacing(4)
        self.title = QtWidgets.QLabel()
        self.date = QtWidgets.QLabel()
        for label in (self.title, self.date):
            label.setSizePolicy(
                QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
            )
        layout.addWidget(self.title)
        layout.addWidget(self.date)
        # hug the text: no phantom padding making every row taller than it is
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)


class ToggleSwitch(QtWidgets.QCheckBox):
    """check box drawn as a real sliding toggle: pill groove + round knob.
    painted by hand because qss indicators can never draw a knob themselves"""

    groove_width = 34.0
    groove_height = 18.0

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def _groove(self):
        y = self.rect().center().y() - self.groove_height / 2.0
        return QtCore.QRectF(self.rect().left(), y, self.groove_width, self.groove_height)

    def hitButton(self, pos):
        # the whole widget is clickable, not just the pill
        return self.rect().contains(pos)

    def sizeHint(self):
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self.text()) if self.text() else 0
        width = int(self.groove_width + 8 + text_width)
        return QtCore.QSize(width, max(22, fm.height() + 4))

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)

        palette = self.palette()
        groove = self._groove()

        if self.isChecked():
            track = palette.color(QtGui.QPalette.Highlight)
            knob_color = palette.color(QtGui.QPalette.HighlightedText)
        else:
            track = palette.color(QtGui.QPalette.Text)
            track.setAlpha(60)
            knob_color = palette.color(QtGui.QPalette.Text)
            knob_color.setAlpha(210)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(groove, groove.height() / 2.0, groove.height() / 2.0)

        radius = groove.height() / 2.0 - 3.0
        if self.isChecked():
            center_x = groove.right() - groove.height() / 2.0
        else:
            center_x = groove.left() + groove.height() / 2.0
        painter.setBrush(knob_color)
        painter.drawEllipse(
            QtCore.QPointF(center_x, groove.center().y()), radius, radius
        )

        if self.text():
            painter.setPen(palette.color(QtGui.QPalette.Text))
            text_rect = QtCore.QRectF(
                groove.right() + 8,
                groove.top() - 8,
                max(0.0, self.rect().right() - groove.right() - 8),
                groove.height() + 16,
            )
            painter.drawText(text_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                              self.text())
