"""QImage provider: Qt renders natively, never calling Python from paint()."""

from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtGui import QImage
from urllib.parse import unquote


class VideoImageProvider(QQuickImageProvider):
    def __init__(self, streams):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.streams = streams

    def requestImage(self, ident, size, requested_size):
        player = self.streams.players.get(unquote(ident.split("?")[0]))
        image = player.image if player and player.phase == "receiving" else QImage()
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image
