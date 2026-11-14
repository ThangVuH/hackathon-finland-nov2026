import cv2
from pathlib import Path
import multiprocessing
import pymupdf

from schema.extractor_schema import Document, Page
from extractors.raster_extractor import extract_ocr, OCR_CONFIG, MAX_IMAGE_PIXELS, MAX_DETECTED_LINES, MAX_DRAWINGS

def is_scanned_page(pdf_page, native_text):

    if len(native_text.strip()) >= 30:
        return False

    image_info = pdf_page.get_image_info()

    if not image_info:
        return False

    page_area = (
        pdf_page.rect.width *
        pdf_page.rect.height
    )

    image_area = 0

    for info in image_info:

        bbox = pymupdf.Rect(info["bbox"])
        image_area += bbox.intersect(
            pdf_page.rect
        ).get_area()

    coverage = image_area / max(page_area, 1)

    return coverage >= 0.35


def extract_native_text(pdf_page):

    texts = []

    blocks = pdf_page.get_text("dict")["blocks"]

    for block in blocks:

        if "lines" not in block:
            continue

        for line in block["lines"]:

            for span in line["spans"]:

                content = span["text"].strip()

                if not content:
                    continue

                texts.append({
                    "content": content,
                    "bbox": list(span["bbox"]),
                    "source": "native"
                })

    return texts


def extract_pdf_geometry(pdf_page):

    geometry = []

    drawings = pdf_page.get_drawings()

    if len(drawings) > MAX_DRAWINGS:
        return geometry

    for drawing in drawings:

        for item in drawing["items"]:

            kind = item[0]

            if kind == "l":

                p1, p2 = item[1], item[2]

                geometry.append({
                    "type": "line",
                    "coordinates": [
                        p1.x, p1.y,
                        p2.x, p2.y
                    ]
                })

            elif kind == "re":

                rect = item[1]

                geometry.append({
                    "type": "rectangle",
                    "coordinates": [
                        rect.x0,
                        rect.y0,
                        rect.x1,
                        rect.y1
                    ]
                })

            elif kind == "c":

                points = item[1:]

                geometry.append({
                    "type": "curve",
                    "coordinates": [
                        [p.x, p.y]
                        for p in points
                    ]
                })

            if len(geometry) >= MAX_DETECTED_LINES:
                return geometry

    return geometry


def extract_pdf_ocr(pdf_page, languages=None):

    matrix = pymupdf.Matrix(
        OCR_CONFIG["zoom"],
        OCR_CONFIG["zoom"]
    )

    pix = pdf_page.get_pixmap(
        matrix=matrix,
        alpha=False
    )

    if pix.width * pix.height > MAX_IMAGE_PIXELS:
        raise ValueError("Rendered PDF page too large")

    image_bytes = pix.tobytes("png")

    import numpy as np

    image = cv2.imdecode(
        np.frombuffer(image_bytes, dtype=np.uint8),
        cv2.IMREAD_COLOR
    )

    if image is None:
        raise ValueError("Cannot decode rendered PDF page")

    # Convert rendered pixel coordinates to PDF points.
    scale_x = pdf_page.rect.width / pix.width
    scale_y = pdf_page.rect.height / pix.height

    return extract_ocr(
        image,
        languages=languages,
        coordinate_scale=(scale_x, scale_y)
    )

def _pdf_page_worker(
    file_path,
    page_index,
    languages,
    connection
):

    try:
        with pymupdf.open(file_path) as pdf:

            pdf_page = pdf[page_index]

            native_text = extract_native_text(pdf_page)

            raw_text = " ".join(
                item["content"]
                for item in native_text
            )

            texts = native_text

            # OCR fallback
            if is_scanned_page(pdf_page, raw_text):

                try:
                    texts = extract_pdf_ocr(
                        pdf_page,
                        languages=languages
                    )

                except Exception as e:
                    print(
                        f"Page {page_index + 1} OCR error: {e}"
                    )

            # Vector geometry
            geometry = extract_pdf_geometry(pdf_page)

            connection.send({
                "success": True,
                "width": pdf_page.rect.width,
                "height": pdf_page.rect.height,
                "texts": texts,
                "geometry": geometry
            })

    except Exception as e:

        connection.send({
            "success": False,
            "error": str(e)
        })

    finally:
        connection.close()


def process_pdf_page(
    file_path,
    page_index,
    languages=None,
    timeout=60
):

    ctx = multiprocessing.get_context("spawn")

    parent_conn, child_conn = ctx.Pipe(
        duplex=False
    )

    process = ctx.Process(
        target=_pdf_page_worker,
        args=(
            file_path,
            page_index,
            languages,
            child_conn
        )
    )

    process.start()
    child_conn.close()

    try:

        if not parent_conn.poll(timeout):

            process.terminate()
            process.join()

            return None

        result = parent_conn.recv()

        process.join(timeout=5)

        if process.is_alive():
            process.terminate()
            process.join()

        if not result["success"]:
            print(
                f"Page {page_index + 1}: "
                f"{result['error']}"
            )
            return None

        return result

    except (EOFError, OSError) as e:

        if process.is_alive():
            process.terminate()

        process.join()

        print(
            f"Page {page_index + 1} failed: {e}"
        )

        return None

    finally:
        parent_conn.close()


def extract_pdf(
    file_path,
    languages=None,
    page_timeout=60
):

    file_path = Path(file_path)

    with pymupdf.open(file_path) as pdf:
        page_count = pdf.page_count

    document = Document(
        document_id=file_path.stem,
        source_file=str(file_path),
        format="pdf"
    )

    for page_index in range(page_count):

        result = process_pdf_page(
            str(file_path),
            page_index,
            languages=languages,
            timeout=page_timeout
        )

        if result is None:

            print(
                f"Skipping page {page_index + 1}"
            )

            continue

        page = Page(
            page_number=page_index + 1,
            width=result["width"],
            height=result["height"],
            unit="pt"
        )

        page.texts = result["texts"]
        page.geometry = result["geometry"]

        document.pages.append(page)

    return document

