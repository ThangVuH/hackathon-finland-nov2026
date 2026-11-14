import json
from pathlib import Path

from pipeline import ingest_document

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
DATA_DIR = PROJECT_ROOT.parent / "data_folder"/ "junction-dataset-preview"

INPUT_DIR = DATA_DIR/"data"
OUTPUT_DIR = DATA_DIR.parent/"output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)    

def process_file(file_path):
    try:
        document = ingest_document(file_path)
        output_path = (
            OUTPUT_DIR /
            f"{document.document_id}.json"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                document.to_dict(),
                f,
                indent=2,
                ensure_ascii=False
            )
        print(f"[SUCCESS] {file_path}")
    except Exception as e:
        print(f"[ERROR] {file_path}: {e}")

def main():
    supported = set([
        ".pdf", ".png", ".jpg", ".jpeg",
        ".dxf", ".dwg", ".ifc", ".svg"
    ])
    for file_path in INPUT_DIR.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in supported:
            process_file(file_path)

if __name__ == "__main__":
    main()
