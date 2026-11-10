import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


class PdfNoDisponible(Exception):
    """El servidor no puede convertir el documento a PDF en este momento."""


def pdf_disponible() -> bool:
    return bool(settings.DOCUMENTOS_PDF and shutil.which(settings.LIBREOFFICE_BIN))


def convertir_a_pdf(contenido: bytes, sufijo: str = ".docx") -> bytes:
    if not pdf_disponible():
        logger.warning("Conversión PDF desactivada o LibreOffice no disponible.")
        raise PdfNoDisponible(
            "LibreOffice no está disponible o el PDF está desactivado."
        )
    if sufijo not in {".docx", ".xlsx"}:
        raise ValueError("Formato de conversión no soportado.")
    with tempfile.TemporaryDirectory() as tmp:
        directorio = Path(tmp)
        ruta = directorio / f"documento{sufijo}"
        ruta.write_bytes(contenido)
        perfil = (directorio / "lo_profile").as_uri()
        try:
            resultado = subprocess.run(
                [
                    settings.LIBREOFFICE_BIN,
                    "--headless",
                    "--norestore",
                    "--nolockcheck",
                    f"-env:UserInstallation={perfil}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmp,
                    str(ruta),
                ],
                env={**os.environ, "HOME": tmp},
                capture_output=True,
                timeout=settings.LIBREOFFICE_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning(
                "LibreOffice no pudo convertir: %s; stderr=%s",
                exc,
                getattr(exc, "stderr", ""),
            )
            raise PdfNoDisponible(
                "LibreOffice no pudo completar la conversión."
            ) from exc
        pdf = directorio / "documento.pdf"
        if resultado.returncode != 0 or not pdf.is_file():
            logger.warning(
                "Error de LibreOffice (código %s); stderr=%s",
                resultado.returncode,
                resultado.stderr,
            )
            raise PdfNoDisponible("LibreOffice no generó el PDF.")
        contenido_pdf = pdf.read_bytes()
        if not contenido_pdf.startswith(b"%PDF"):
            logger.warning(
                "LibreOffice generó un archivo PDF inválido; stderr=%s",
                resultado.stderr,
            )
            raise PdfNoDisponible("LibreOffice generó un PDF inválido.")
        return contenido_pdf
