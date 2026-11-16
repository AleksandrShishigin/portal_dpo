from pathlib import Path
from PIL import Image
from pypdf import PdfReader
from rest_framework.exceptions import ValidationError
import warnings
import logging

# Parsers must not emit fragments of uploaded documents into application logs.
_pdf_logger = logging.getLogger('pypdf')
_pdf_logger.addHandler(logging.NullHandler())
_pdf_logger.propagate = False

MAX_SIZE = 10 * 1024 * 1024


def validate_document(file):
    if not file.size or file.size > MAX_SIZE:
        raise ValidationError({'file': 'Допустим непустой файл размером до 10 МБ.'})
    suffix = Path(file.name).suffix.lower()
    try:
        header = file.read(8)
        file.seek(0)
        if suffix == '.pdf' and header.startswith(b'%PDF-'):
            reader = PdfReader(file, strict=True)
            if reader.is_encrypted or not len(reader.pages):
                raise ValueError('Invalid PDF')
            mime = 'application/pdf'
        elif suffix in {'.jpg', '.jpeg', '.png'}:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                image = Image.open(file)
                expected = 'PNG' if suffix == '.png' else 'JPEG'
                if image.format != expected:
                    raise ValueError('Wrong image format')
                image.verify()
            mime = 'image/png' if expected == 'PNG' else 'image/jpeg'
        else:
            raise ValueError('Unsupported file')
    except Exception:
        raise ValidationError({'file': 'Нужен корректный PDF, JPEG или PNG с соответствующим расширением; защищённые PDF не принимаются.'})
    finally:
        file.seek(0)
    return mime
