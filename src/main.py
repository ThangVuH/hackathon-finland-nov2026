import json
from pathlib import Path
import pytesseract
import json
from pathlib import Path
import yaml
from pipeline.extractor_pipeline import ingest_document
from pipeline.extractor_pipeline import ingest_document

# Load the YAML configuration file
CONFIG_PATH = Path.cwd()/"config.yml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

INPUT_DIR = Path(config["input_dir"])
OUTPUT_DIR = Path(config["output_dir"])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
pytesseract.pytesseract.tesseract_cmd =Path(config["tesseract"])

def process_file(file_path):
    try:
        document = ingest_document(file_path)
        output_path = OUTPUT_DIR / f"{document.document_id}_{document.format}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                document.to_dict(),
                f,
                indent=2,
                ensure_ascii=False
            )
        print(f"[SUCCESS] {file_path} to {output_path}")
    except Exception as e:
        print(f"[ERROR] {file_path}: {e}")

def main():
    # Load supported extensions from YAML and convert to a set
    supported = set(config["supported_extensions"])
    
    for file_path in INPUT_DIR.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in supported:
            process_file(file_path)

if __name__ == "__main__":
    main()