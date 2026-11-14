from pathlib import Path

from extractors.pdf_extractor import extract_pdf
from extractors.raster_extractor import extract_raster
from extractors.dxf_extractor import extract_dxf
from extractors.svg_extractor import extract_svg
from extractors.dwg_extractor import extract_dwg
from extractors.ifc_extractor import extract_ifc

EXTRACTORS = {
    ".pdf": extract_pdf,
    ".png": extract_raster,
    ".jpg": extract_raster,
    ".jpeg": extract_raster,
    ".dxf": extract_dxf,
    ".svg": extract_svg,
    ".dwg": extract_dwg,
    ".ifc": extract_ifc
}

def ingest_document(file_path):

    file_path = Path(file_path)

    extension = file_path.suffix.lower()

    extractor = EXTRACTORS.get(extension)

    if extractor is None:
        raise ValueError(
            f"Unsupported file format: {extension}"
        )

    document = extractor(str(file_path))

    return document