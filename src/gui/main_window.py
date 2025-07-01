import sys
import os
import configparser
import webbrowser

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QComboBox, QHBoxLayout,
    QMessageBox, QFrame, QGraphicsDropShadowEffect, QStackedLayout
)
from PyQt6.QtCore import QThread, Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QIcon, QColor, QFont, QMovie

_current_file_path = os.path.abspath(__file__)
GUI_DIR = os.path.dirname(_current_file_path)
SRC_DIR = os.path.dirname(GUI_DIR)
PROJECT_ROOT = os.path.dirname(SRC_DIR)

ASSETS_DIR = os.path.join(SRC_DIR, 'assets')
CONFIG_FILE = os.path.join(PROJECT_ROOT, 'config.ini')
APP_ICON = os.path.join(ASSETS_DIR, 'icon.png')
SPINNER_GIF = os.path.join(ASSETS_DIR, 'spinner.gif')
STYLESHEET_FILE = os.path.join(ASSETS_DIR, 'styles.qss')

# Импорты из нашего проекта
try:
    from ..core.worker import AnalysisWorker
    from ..core.steam_network import CURRENCIES
    from .widgets.numeric_item import NumericTableWidgetItem
    from .widgets.card_list_dialog import CardListDialog
except ImportError as e:
    # Этот блок нужен для отладки, если структура проекта нарушена
    print("Критическая ошибка: Не удалось импортировать модули.", e)
    sys.exit(1)


def load_stylesheet():
    try:
        with open(STYLESHEET_FILE, "r", encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Предупреждение: Файл стилей не найден: {STYLESHEET_FILE}")
        return ""


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.thread = None
        self.currency_symbol = "RUB"
        self.init_ui()
        self.load_settings()

        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(300)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()

    def init_ui(self):
        self.setObjectName("mainWindow")
        self.setWindowTitle("Помощник по значкам Steam")
        self.setGeometry(100, 100, 900, 800)
        self.setWindowIcon(QIcon(APP_ICON))
        self.setStyleSheet(load_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 32, 32, 32)
        main_layout.setSpacing(24)

        title = QLabel("Анализатор значков Steam")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        input_frame = QFrame()
        input_frame.setObjectName("inputFrame")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setSpacing(18)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Ваш Steam Web API Key...")
        input_layout.addWidget(self.api_key_input)

        self.user_id_input = QLineEdit()
        self.user_id_input.setPlaceholderText("Ваш SteamID64 или Custom URL...")
        input_layout.addWidget(self.user_id_input)
        main_layout.addWidget(input_frame)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(16)
        controls_layout.addWidget(QLabel("Валюта:"))
        self.currency_combo = QComboBox()
        self.currency_combo.setObjectName("currencyCombo")
        self._populate_currency_combo()
        self.currency_combo.currentTextChanged.connect(self.update_currency_symbol)
        controls_layout.addWidget(self.currency_combo)
        controls_layout.addStretch()

        self.start_button = QPushButton("\U0001F680  Начать анализ")
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.start_analysis)
        self.apply_shadow(self.start_button)
        controls_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("\U0001F6D1  Стоп")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.clicked.connect(self.stop_analysis)
        self.stop_button.setEnabled(False)
        self.apply_shadow(self.stop_button)
        controls_layout.addWidget(self.stop_button)
        main_layout.addLayout(controls_layout)

        self.status_label = QLabel("Готов к работе.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setObjectName("statusLabel")
        main_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.loading_spinner = QLabel()
        self.loading_spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_spinner.setVisible(False)
        self.spinner_movie = QMovie(SPINNER_GIF)
        self.loading_spinner.setMovie(self.spinner_movie)
        main_layout.addWidget(self.loading_spinner)

        self.table_stack = QStackedLayout()
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Игра", "Стоимость", "Купить", "Действие"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self.open_game_page_from_table)
        
        self.placeholder_label = QLabel("\U0001F4CA\nРезультаты анализа появятся здесь...")
        self.placeholder_label.setObjectName("placeholderLabel")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.table_stack.addWidget(self.placeholder_label)
        self.table_stack.addWidget(self.table)
        main_layout.addLayout(self.table_stack)

    def apply_shadow(self, widget):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 3)
        widget.setGraphicsEffect(shadow)

    def _populate_currency_combo(self):
        for code, data in CURRENCIES.items():
            flag_emoji = "".join([chr(0x1F1E6 + ord(c.upper()) - ord('A')) for c in data['flag']])
            self.currency_combo.addItem(f"{flag_emoji} {code}", userData=code)

    def _get_selected_currency_code(self):
        return self.currency_combo.currentData()

    def update_currency_symbol(self, text):
        self.currency_symbol = CURRENCIES.get(self._get_selected_currency_code(), {}).get('code', 'RUB')

    def start_analysis(self):
        api_key = self.api_key_input.text().strip()
        user_id = self.user_id_input.text().strip()
        currency_code = self._get_selected_currency_code()
        
        if not api_key or not user_id:
            self.show_error_message("API ключ и ID пользователя должны быть заполнены.")
            return
        
        self.table_stack.setCurrentWidget(self.table)
        self.table.setRowCount(0)
        self.status_label.setText("Подготовка к анализу...")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        self.loading_spinner.setVisible(True)
        self.spinner_movie.start()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        
        self.save_settings()
        currency_id = CURRENCIES[currency_code]['id']
        self.thread = QThread()
        self.worker = AnalysisWorker(api_key, user_id, currency_id)
        self.worker.moveToThread(self.thread)

        self.worker.progress_update.connect(self.update_progress)
        self.worker.result_ready.connect(self.add_result_to_table)
        self.worker.finished.connect(self.on_analysis_finished)
        self.worker.error_occurred.connect(self.on_error)
        
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def stop_analysis(self):
        if self.worker:
            self.status_label.setText("Остановка...")
            self.stop_button.setEnabled(False)
            self.worker.cancel()

    def on_analysis_finished(self):
        if self.table.rowCount() == 0:
            self.table_stack.setCurrentWidget(self.placeholder_label)
        
        current_status = self.status_label.text()
        if self.worker and self.worker._is_cancelled:
            self.status_label.setText("Анализ был отменен пользователем.")
        elif "ошибка" not in current_status.lower():
            self.status_label.setText("Анализ завершен!")
            
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.loading_spinner.setVisible(False)
        self.spinner_movie.stop()
        self.progress_bar.setFormat("")
        
        if self.thread:
            self.thread.quit()
            self.thread.wait()

    def on_error(self, message):
        self.show_error_message(message, "Ошибка выполнения")
        self.status_label.setText(f"Ошибка: {message}")
        self.on_analysis_finished()

    def show_error_message(self, text, title="Ошибка"):
        msg_box = QMessageBox(self)
        msg_box.setStyleSheet(self.styleSheet())
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText(text)
        msg_box.setWindowTitle(title)
        msg_box.exec()

    def update_progress(self, value, maximum, text):
        self.progress_bar.setMaximum(maximum)
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat(f"{value} / {maximum}")
        self.status_label.setText(text)

    def add_result_to_table(self, result):
        row = self.table.rowCount()
        self.table.insertRow(row)

        game_item = QTableWidgetItem(result['game'])
        game_item.setData(Qt.ItemDataRole.UserRole, result)
        self.table.setItem(row, 0, game_item)
        
        cost_item = NumericTableWidgetItem(f"{result['cost']:.2f}")
        cost_item.setData(Qt.ItemDataRole.UserRole, result['cost'])
        self.table.setItem(row, 1, cost_item)

        buy_count_item = NumericTableWidgetItem(str(result['to_buy_count']))
        buy_count_item.setData(Qt.ItemDataRole.UserRole, result['to_buy_count'])
        self.table.setItem(row, 2, buy_count_item)
        
        if result['to_buy_count'] > 0:
            details_button = QPushButton("Показать...")
            details_button.setStyleSheet("padding: 5px; font-size: 9pt;")
            details_button.clicked.connect(lambda _, r=result: self.show_card_dialog(r))
            self.table.setCellWidget(row, 3, details_button)

    def show_card_dialog(self, result_data):
        dialog = CardListDialog(
            result_data['game'], 
            result_data['to_buy_list'], 
            self._get_selected_currency_code(), 
            self
        )
        dialog.exec()
        
    def open_game_page_from_table(self, mi):
        result_data = self.table.item(mi.row(), 0).data(Qt.ItemDataRole.UserRole)
        if result_data and result_data.get('appid'):
            webbrowser.open(f"https://store.steampowered.com/app/{result_data['appid']}")

    def save_settings(self):
        config = configparser.ConfigParser()
        config['Steam'] = {
            'api_key': self.api_key_input.text(),
            'user_id': self.user_id_input.text(),
            'currency': self._get_selected_currency_code() or 'RUB'
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)

    def load_settings(self):
        config = configparser.ConfigParser()
        if config.read(CONFIG_FILE, encoding='utf-8'):
            self.api_key_input.setText(config.get('Steam', 'api_key', fallback=''))
            self.user_id_input.setText(config.get('Steam', 'user_id', fallback=''))
            currency_code = config.get('Steam', 'currency', fallback='RUB')
            index = self.currency_combo.findData(currency_code)
            if index != -1:
                self.currency_combo.setCurrentIndex(index)

    def closeEvent(self, event):
        self.save_settings()
        if self.thread and self.thread.isRunning():
            self.stop_analysis()
            self.thread.wait(2000)
        super().closeEvent(event)