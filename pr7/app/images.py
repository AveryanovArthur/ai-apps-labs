import io
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

load_dotenv()

UPLOAD_MAX_BYTES = int(float(os.getenv("UPLOAD_MAX_MB", "10")) * 1024 * 1024)
IMAGE_MAX_SIDE = int(os.getenv("IMAGE_MAX_SIDE", "1600"))
IMAGE_MIN_SIDE = int(os.getenv("IMAGE_MIN_SIDE", "200"))
IMAGE_MAX_PIXELS = int(os.getenv("IMAGE_MAX_PIXELS", "40000000"))
IMAGE_FORMAT = os.getenv("IMAGE_FORMAT", "PNG").upper()
IMAGE_JPEG_QUALITY = int(os.getenv("IMAGE_JPEG_QUALITY", "90"))

Image.MAX_IMAGE_PIXELS = IMAGE_MAX_PIXELS * 2


class ImageError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class PreparedImage:
    data: bytes
    mime: str
    original: dict
    sent: dict
    sharpness: float = 0.0


def _open(content: bytes):
    try:
        probe = Image.open(io.BytesIO(content))
        width, height = probe.size
        if width * height > IMAGE_MAX_PIXELS:
            raise ImageError(
                f"Зображення завелике в пікселях: {width}×{height}. "
                f"Допустимо не більше {IMAGE_MAX_PIXELS // 1_000_000} мегапікселів.",
                413,
            )
        probe.verify()
        image = Image.open(io.BytesIO(content))
        image.load()
    except ImageError:
        raise
    except Image.DecompressionBombError as exc:
        raise ImageError("Зображення завелике в пікселях.", 413) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageError(
            "Файл не є зображенням або пошкоджений. Надішліть PNG, JPEG або WebP.", 415
        ) from exc
    return image, (width, height)


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")


def _sharpness(image: Image.Image) -> float:
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    return round(ImageStat.Stat(edges).stddev[0], 2)


def prepare(content: bytes) -> PreparedImage:
    if not content:
        raise ImageError("Файл порожній.", 400)
    if len(content) > UPLOAD_MAX_BYTES:
        raise ImageError(
            f"Файл завеликий: {len(content) / 1024 / 1024:.1f} МБ, "
            f"найбільший розмір — {UPLOAD_MAX_BYTES / 1024 / 1024:.0f} МБ.",
            413,
        )

    image, (width, height) = _open(content)
    image = _to_rgb(ImageOps.exif_transpose(image))

    if min(image.size) < IMAGE_MIN_SIDE:
        raise ImageError(
            f"Зображення замале ({image.width}×{image.height}): цифри не розібрати. "
            "Перезніміть документ ближче або з вищою роздільністю.",
            422,
        )

    longest = max(image.size)
    if longest > IMAGE_MAX_SIDE:
        scale = IMAGE_MAX_SIDE / longest
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )

    buffer = io.BytesIO()
    if IMAGE_FORMAT == "JPEG":
        image.save(buffer, "JPEG", quality=IMAGE_JPEG_QUALITY, optimize=True)
        mime = "image/jpeg"
    else:
        image.save(buffer, "PNG")
        mime = "image/png"
    data = buffer.getvalue()

    return PreparedImage(
        data=data,
        mime=mime,
        original={"width": width, "height": height, "bytes": len(content)},
        sent={"width": image.width, "height": image.height, "bytes": len(data)},
        sharpness=_sharpness(image),
    )