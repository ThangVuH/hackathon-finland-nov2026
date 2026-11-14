import ezdxf

from ezdxf import bbox as dxf_bbox
from pathlib import Path

from schema import Document, Page


def extract_dxf(file_path):

    path_obj = Path(file_path)
    doc = ezdxf.readfile(path_obj)
    modelspace = doc.modelspace()

    # Determine drawing extents
    extents = dxf_bbox.extents(modelspace)

    if extents.has_data:
        width = extents.extmax.x - extents.extmin.x
        height = extents.extmax.y - extents.extmin.y
        min_x = extents.extmin.x
        min_y = extents.extmin.y
    else:
        width, height = 0, 0
        min_x, min_y = 0, 0

    document = Document(
        document_id=path_obj.stem,
        source_file=file_path,
        format="dxf"
    )

    page = Page(
        page_number=1,
        width=width,
        height=height,
        unit="drawing_units"
    )

    def normalize(x, y):
        return [
            x - min_x,
            max_y - y
        ]

    max_y = min_y + height

    for entity in modelspace:

        entity_type = entity.dxftype()

        # TEXT
        if entity_type in ["TEXT", "MTEXT"]:

            content = (
                entity.dxf.text
                if entity_type == "TEXT"
                else entity.text
            )

            if entity_type == "TEXT":
                x, y = entity.dxf.insert.x, entity.dxf.insert.y
            else:
                x, y = entity.dxf.insert.x, entity.dxf.insert.y

            x, y = normalize(x, y)

            page.texts.append({
                "content": content,
                "bbox": [x, y, x, y],
                "source": "native"
            })

        # LINE
        elif entity_type == "LINE":

            start = normalize(
                entity.dxf.start.x,
                entity.dxf.start.y
            )

            end = normalize(
                entity.dxf.end.x,
                entity.dxf.end.y
            )

            page.geometry.append({
                "type": "line",
                "coordinates": [
                    *start,
                    *end
                ]
            })

        # LWPOLYLINE
        elif entity_type == "LWPOLYLINE":

            points = [
                normalize(x, y)
                for x, y, *_ in entity.get_points()
            ]

            page.geometry.append({
                "type": "polyline",
                "coordinates": points,
                "properties": {
                    "closed": entity.closed
                }
            })

        # CIRCLE
        elif entity_type == "CIRCLE":

            center = normalize(
                entity.dxf.center.x,
                entity.dxf.center.y
            )

            page.geometry.append({
                "type": "circle",
                "coordinates": [
                    *center,
                    entity.dxf.radius
                ]
            })

        # ARC
        elif entity_type == "ARC":

            center = normalize(
                entity.dxf.center.x,
                entity.dxf.center.y
            )

            page.geometry.append({
                "type": "arc",
                "coordinates": [
                    *center,
                    entity.dxf.radius,
                    entity.dxf.start_angle,
                    entity.dxf.end_angle
                ]
            })

    document.pages.append(page)
    return document