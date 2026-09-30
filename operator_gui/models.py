"""Small bounded Qt models; no robot operations in view code."""

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSortFilterProxyModel, Qt, Slot
from PySide6.QtGui import QGuiApplication

ENTRY = Qt.ItemDataRole.UserRole + 1
LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class Rows(QAbstractListModel):
    def __init__(self, parent=None, limit=2000):
        super().__init__(parent)
        self.items = []
        self.limit = limit

    def roleNames(self):
        return {ENTRY: b"entry"}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and 0 <= index.row() < len(self.items) and role == ENTRY:
            return self.items[index.row()]
        return None

    def replace(self, items):
        self.beginResetModel()
        self.items = list(items)[-self.limit:]
        self.endResetModel()

    def append(self, item):
        if len(self.items) >= self.limit:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self.items.pop(0)
            self.endRemoveRows()
        index = len(self.items)
        self.beginInsertRows(QModelIndex(), index, index)
        self.items.append(item)
        self.endInsertRows()

    def update_named(self, name, values):
        for row, item in enumerate(self.items):
            if item.get("name") == name:
                self.items[row] = item | values
                self.dataChanged.emit(self.index(row), self.index(row), [ENTRY])
                return


class ParameterFilter(QSortFilterProxyModel):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.group = self.search = ""
        self.setSourceModel(model)

    def configure(self, group, search):
        self.group, self.search = group, search.casefold()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        name = self.sourceModel().items[row]["name"]
        return (not self.group or name.split(".", 1)[0] == self.group) and self.search in name.casefold()


class LogFilter(QSortFilterProxyModel):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.setSourceModel(model)
        self.level = 10
        self.search = ""
        self.source = ""

    @Slot(result=str)
    def text(self):
        lines = []
        for row in range(self.rowCount()):
            item = self.data(self.index(row, 0), ENTRY)
            lines.append(f"{item['time']} [{item['level']}] {item['source']}: {item['message']}")
        return "\n".join(lines)

    @Slot()
    def copyAll(self):
        QGuiApplication.clipboard().setText(self.text())

    @Slot(str, str, str)
    def configure(self, level, search, source):
        self.level = LEVELS.get(level, 10)
        self.search = search.casefold()
        self.source = source.casefold()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        item = self.sourceModel().items[row]
        return (LEVELS.get(item["level"], 20) >= self.level
                and self.source in item["source"].casefold()
                and self.search in (item["source"] + " " + item["message"]).casefold())
