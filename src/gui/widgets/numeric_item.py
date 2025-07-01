from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtCore import Qt

class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            self_data = float(self.data(Qt.ItemDataRole.UserRole))
            other_data = float(other.data(Qt.ItemDataRole.UserRole))
            return self_data < other_data
        except (ValueError, TypeError):
            return super().__lt__(other)