from pathlib import Path
import cv2
import pytesseract
import numpy as np

from pytesseract import Output
from schema import Document, Page

OCR_LANGUAGES = {
    "english": "eng",
    "french": "fra",
    "german": "deu",
    "finnish": "fin",
    "spanish": "spa",
    "italian": "ita",
    "dutch": "nld",
    "portuguese": "por",
}
DEFAULT_LANGUAGES = [
    "english",
    "french",
    "german",
]
OCR_CONFIG = {
    "psm": 11,
    "timeout": 30,
    "min_confidence": 30,
    "zoom": 3,
}
MAX_IMAGE_PIXELS = 40_000_000
MAX_DETECTED_LINES = 20_000
MAX_DRAWINGS = 10_000

def get_tesseract_languages(languages=None):

    languages = languages or DEFAULT_LANGUAGES

    unknown = set(languages) - set(OCR_LANGUAGES)

    if unknown:
        raise ValueError(
            f"Unsupported OCR languages: {unknown}"
        )

    return "+".join(
        OCR_LANGUAGES[language]
        for language in languages
    )

def preprocess_image(image):

    if len(image.shape) == 3:
        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )
    else:
        gray = image.copy()

    denoised = cv2.fastNlMeansDenoising(
        gray,
        None,
        10,
        7,
        21
    )

    processed = cv2.threshold(
        denoised,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )[1]

    return gray, processed


def extract_ocr(
    image,
    languages=None,
    coordinate_scale=(1.0, 1.0)
):

    _, processed = preprocess_image(image)

    lang = get_tesseract_languages(languages)

    ocr = pytesseract.image_to_data(
        processed,
        lang=lang,
        output_type=Output.DICT,
        config=f"--psm {OCR_CONFIG['psm']}",
        timeout=OCR_CONFIG["timeout"]
    )

    texts = []

    scale_x, scale_y = coordinate_scale

    for i, content in enumerate(ocr["text"]):

        # Word-level results only
        if ocr["level"][i] != 5:
            continue

        content = content.strip()

        if not content:
            continue

        confidence = float(ocr["conf"][i])

        if confidence < OCR_CONFIG["min_confidence"]:
            continue

        x = ocr["left"][i]
        y = ocr["top"][i]
        w = ocr["width"][i]
        h = ocr["height"][i]

        texts.append({
            "content": content,
            "bbox": [
                x * scale_x,
                y * scale_y,
                (x + w) * scale_x,
                (y + h) * scale_y
            ],
            "confidence": confidence / 100,
            "source": "ocr",
            "extraction_method": "tesseract"
        })

    return texts

def extract_raster_geometry(image):

    gray, processed = preprocess_image(image)

    edges = cv2.Canny(
        gray,
        50,
        150
    )

    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=80,
        minLineLength=20,
        maxLineGap=5
    )

    geometry = []

    if lines is not None:

        for line in lines[:MAX_DETECTED_LINES]:
            coords = line.flatten()
            if len(coords) == 4:
                x1, y1, x2, y2 = coords

                geometry.append({
                    "type": "line",
                    "coordinates": [
                        int(x1),
                        int(y1),
                        int(x2),
                        int(y2)
                    ]
                })

    # Detect horizontal and vertical table lines
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        15,
        10
    )

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (40, 1)
    )

    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (1, 40)
    )

    horizontal = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        horizontal_kernel
    )

    vertical = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        vertical_kernel
    )

    for mask, orientation in [
        (horizontal, "horizontal"),
        (vertical, "vertical")
    ]:

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in contours:

            x, y, w, h = cv2.boundingRect(contour)

            geometry.append({
                "type": "line",
                "orientation": orientation,
                "coordinates": [
                    x, y,
                    x + w, y + h
                ]
            })

    return geometry[:MAX_DETECTED_LINES]


def extract_raster(
    file_path,
    languages=None
):

    file_path = Path(file_path)

    image = cv2.imread(str(file_path))

    if image is None:
        raise ValueError(
            f"Cannot read image: {file_path}"
        )

    height, width = image.shape[:2]

    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError("Image resolution too large")

    document = Document(
        document_id=file_path.stem,
        source_file=str(file_path),
        format=file_path.suffix.lstrip(".").lower()
    )

    page = Page(
        page_number=1,
        width=width,
        height=height,
        unit="px"
    )

    # 1. OCR
    try:
        page.texts = extract_ocr(
            image,
            languages=languages
        )

    except RuntimeError as e:
        print(f"OCR failed: {e}")

    # 2. Geometry
    page.geometry = extract_raster_geometry(image)

    document.pages.append(page)

    return document
