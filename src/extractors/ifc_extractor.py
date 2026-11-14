import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.unit

from pathlib import Path
from schema import Document, Page


def extract_ifc(file_path):
    
    path_obj = Path(file_path)
    model = ifcopenshell.open(path_obj)

    document = Document(
        document_id=path_obj.stem,
        source_file=file_path,
        format="ifc"
    )

    # IFC has no inherent PDF-like pages.
    # Represent the model as a logical page.
    page = Page(
        page_number=1,
        width=0,
        height=0,
        unit="model_units"
    )

    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(
        model
    )

    semantic_elements = []

    for entity_type in [
        "IfcSpace",
        "IfcWall",
        "IfcDoor",
        "IfcWindow",
        "IfcSlab"
    ]:

        for entity in model.by_type(entity_type):

            properties = (
                ifcopenshell.util.element.get_psets(entity)
            )

            semantic_elements.append({
                "ifc_id": entity.id(),
                "global_id": getattr(
                    entity, "GlobalId", None
                ),
                "type": entity_type,
                "name": getattr(entity, "Name", None),
                "properties": properties
            })

    document.metadata["unit_scale"] = unit_scale
    document.metadata["semantic_elements"] = semantic_elements

    document.pages.append(page)

    return document