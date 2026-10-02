"""Local view manifest. No session, receiver creation or network operations."""
import json
import uuid
from PySide6.QtCore import QObject, Property, Signal, Slot


class VideoViews(QObject):
    changed = Signal()
    added = Signal(str)
    removed = Signal(str)
    requested = Signal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.items = []
        try:
            data = json.loads(path.read_text())
            seen = set()
            for entry in data:
                ident = str(uuid.UUID(entry["id"]))
                if ident not in seen:
                    self.items.append(dict(id=ident, stream=""))
                    seen.add(ident)
        except (OSError, ValueError, KeyError, TypeError):
            pass

    @Property("QVariantList", notify=changed)
    def entries(self):
        return self.items

    @Slot(str, result=str)
    def add(self, stream=""):
        ident = str(uuid.uuid4())
        self.items = self.items + [dict(id=ident, stream=stream)]
        self.changed.emit()
        self.added.emit(ident)
        return ident

    @Slot(str)
    def show(self, stream):
        existing = next((e for e in self.items if e["stream"] == stream), None)
        if existing:
            self.requested.emit(existing["id"])
        else:
            self.add(stream)

    @Slot(str)
    def remove(self, ident):
        self.items = [e for e in self.items if e["id"] != ident]
        self.removed.emit(ident)
        self.changed.emit()

    @Slot(str, str)
    def select(self, ident, stream):
        self.items = [dict(e, stream=stream) if e["id"] == ident else e for e in self.items]
        self.changed.emit()

    @Slot(str, result=str)
    def selected(self, ident):
        return next((e["stream"] for e in self.items if e["id"] == ident), "")

    def clearSelections(self):
        self.items = [dict(e, stream="") for e in self.items]
        self.changed.emit()

    @Slot(result=bool)
    def restore(self):
        try:
            data = json.loads(self.path.read_text())
            ids = list(dict.fromkeys(str(uuid.UUID(e["id"])) for e in data))
        except (OSError, ValueError, KeyError, TypeError):
            return False
        previous = {e["id"]: e for e in self.items}
        self.items = [previous.get(ident, dict(id=ident, stream="")) for ident in ids]
        self.changed.emit()
        for ident in previous.keys() - set(ids):
            self.removed.emit(ident)
        for ident in ids:
            if ident not in previous:
                self.added.emit(ident)
        return True

    @Slot(result=bool)
    def save(self):
        try:
            # Only view identities persist: stream IDs belong to a robot session.
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps([dict(id=e["id"]) for e in self.items]))
            temp.replace(self.path)
            return True
        except OSError:
            return False
