# utils/splash_screen.py

from PySide6.QtWidgets import QSplashScreen
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt, QRect

class SplashScreen(QSplashScreen):
    def __init__(self, pixmap):
        super().__init__(pixmap)
        self.message = ""

    def set_message(self, message):
        self.message = message
        self.showMessage(message, Qt.AlignBottom | Qt.AlignHCenter, Qt.black)

    def drawContents(self, painter):
        pixmap = self.pixmap()
        painter.drawPixmap(0, 0, pixmap)
        font = QFont()
        font.setFamily("Segoe UI")
        font.setPointSize(12)
        painter.setFont(font)
        painter.setPen(QColor(Qt.black))
        painter.drawText(QRect(0, pixmap.height() - 40, pixmap.width(), 20), Qt.AlignCenter, self.message)
