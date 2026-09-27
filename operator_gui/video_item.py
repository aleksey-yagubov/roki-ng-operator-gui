"""QImage provider: Qt renders natively, never calling Python from paint()."""

from PySide6.QtQuick import QQuickImageProvider


class VideoImageProvider(QQuickImageProvider):
    def __init__(self, video):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.video = video

    def requestImage(self, ident, size, requested_size):
        image = self.video.image
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image
