import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import BadRequest


def read_photo(upload):
    if not upload or not upload.filename:
        return None
    data = upload.stream.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise BadRequest("A fotografia não pode exceder 2 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or image.width * image.height > 16_000_000:
                    raise BadRequest("Use uma imagem JPEG, PNG ou WebP até 16 megapíxeis.")
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((512, 512))
                image = image.convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=85)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise BadRequest("A fotografia é inválida. Escolha uma imagem JPEG, PNG ou WebP.") from error
