import subprocess
import tempfile
from pathlib import Path

from extractors.dxf_extractor import extract_dxf


def extract_dwg(file_path):

    file_path = Path(file_path)

    with tempfile.TemporaryDirectory() as temp:

        output_dir = Path(temp)

        subprocess.run(
            [
                "ODAFileConverter",
                str(file_path.parent),
                str(output_dir),
                "ACAD2018",
                "DXF",
                "0",
                "1",
                file_path.name
            ],
            check=True,
            capture_output=True,
            text=True
        )

        converted_file = output_dir / (
            file_path.stem + ".dxf"
        )

        if not converted_file.exists():
            raise RuntimeError(
                "DWG to DXF conversion failed"
            )

        document = extract_dxf(str(converted_file))

        document.source_file = str(file_path)
        document.format = "dwg"

        return document