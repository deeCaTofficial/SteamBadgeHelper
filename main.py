import sys
from PyQt6.QtWidgets import QApplication

try:
    from src.gui.main_window import MainWindow
except ImportError as e:
    print("Ошибка: Не удалось импортировать компоненты приложения.")
    print("Убедитесь, что вы запускаете main.py из корневой папки проекта,")
    print("и что структура папок верна (должна быть папка 'src' с кодом).")
    print(f"Текст ошибки: {e}")
    sys.exit(1)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()