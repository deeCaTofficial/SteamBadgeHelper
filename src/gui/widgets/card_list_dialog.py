import requests
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices

class CardListDialog(QDialog):
    def __init__(self, game_name, cards_to_buy, currency_symbol, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Карточки для '{game_name}'")
        self.setMinimumSize(500, 400)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        layout = QVBoxLayout(self)
        label = QLabel("Кликните по карточке, чтобы открыть ее на Торговой площадке:")
        layout.addWidget(label)

        self.list_widget = QListWidget()
        for card in cards_to_buy:
            price_str = f"~{card['price']:.2f} {currency_symbol}" if card['price'] is not None else "Цена неизвестна"
            item_text = f"{card['name']} ({price_str})"
            
            # Используем requests.utils.quote для корректного кодирования URL
            url_name = requests.utils.quote(card['name'])
            market_url = f"https://steamcommunity.com/market/listings/753/{url_name}"
            
            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.ItemDataRole.UserRole, market_url)
            self.list_widget.addItem(list_item)
        
        self.list_widget.itemClicked.connect(self.open_link)
        layout.addWidget(self.list_widget)
            
    def open_link(self, item):
        url = item.data(Qt.ItemDataRole.UserRole)
        if url:
            QDesktopServices.openUrl(QUrl(url))