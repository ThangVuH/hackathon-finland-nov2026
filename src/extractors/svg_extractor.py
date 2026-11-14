from lxml import etree

from pathlib import Path
from schema import Document, Page


def extract_svg(file_path):

    path_obj = Path(file_path)
    tree = etree.parse(path_obj)
    root = tree.getroot()

    def get_number(value):
        if not value:
            return 0.0

        import re
        match = re.search(r"[-+]?\d*\.?\d+", value)

        return float(match.group()) if match else 0.0

    width = get_number(root.get("width"))
    height = get_number(root.get("height"))

    if root.get("viewBox"):
        viewbox = [
            float(x)
            for x in root.get("viewBox").replace(",", " ").split()
        ]

        if width == 0:
            width = viewbox[2]

        if height == 0:
            height = viewbox[3]

    document = Document(
        document_id=path_obj.stem,
        source_file=file_path,
        format="svg"
    )

    page = Page(
        page_number=1,
        width=width,
        height=height,
        unit="svg_user_units"
    )

    ns = {"svg": "http://www.w3.org/2000/svg"}

    # Extract text
    for element in root.xpath(".//svg:text", namespaces=ns):

        content = "".join(element.itertext()).strip()

        if not content:
            continue

        x = get_number(element.get("x"))
        y = get_number(element.get("y"))

        page.texts.append({
            "content": content,
            "bbox": [x, y, x, y],
            "source": "native"
        })

    # Extract basic geometry
    for element in root.iter():

        tag = element.tag.split("}")[-1]

        if tag == "line":

            x1 = get_number(element.get("x1"))
            y1 = get_number(element.get("y1"))
            x2 = get_number(element.get("x2"))
            y2 = get_number(element.get("y2"))

            page.geometry.append({
                "type": "line",
                "coordinates": [x1, y1, x2, y2]
            })

        elif tag == "rect":

            x = get_number(element.get("x"))
            y = get_number(element.get("y"))
            w = get_number(element.get("width"))
            h = get_number(element.get("height"))

            page.geometry.append({
                "type": "rectangle",
                "coordinates": [
                    x, y, x + w, y + h
                ]
            })

        elif tag == "circle":

            cx = get_number(element.get("cx"))
            cy = get_number(element.get("cy"))
            r = get_number(element.get("r"))

            page.geometry.append({
                "type": "circle",
                "coordinates": [cx, cy, r]
            })

    document.pages.append(page)

    return document