# Stoa — version 1.1

A floor plan, a question, and an answer you can tell is reliable.

The front end, `STOA-eyes`, opens a plan and asks a question. It runs with Node.js and a vision-model key. The trained detector is optional: it counts windows and doors, and the system marks that count **reliable** only when its total equals the vision model's and the rectangles overlap. Otherwise the count is **to check**. Disagreed rectangles stay highlighted, and a click keeps or removes them. A file outside the domain (IFC, PDF, archive sheet) is refused, and no count is invented.

```
STOA-eyes/     the app (chat, plan, boxes)
counting/      the detector, the arbitration rule, the measurement
eda/eda.ipynb  the Junction preview exploration
```

## Run the application

Node.js 22 or newer is enough. PyTorch is not part of launching the site. The trained weights are already in the repo; nobody has to retrain them.

```powershell
cd STOA-eyes
npm install
npm run dev
```

The dev server prints a URL, usually `http://localhost:8080/`.

Put the vision model key in `STOA-eyes/.env`. That file must not be committed:

```
LOVABLE_API_KEY=your-key
```

With only this, the site opens a plan and answers. A window or door count is marked **not checked**, because the trained detector did not confirm it. Any other question (rooms, columns, area) needs the key. On a terminal that was open before Node was installed, `npm` is unknown. Open a new one.

`STOA_API_KEY` in the same `.env` is used before `LOVABLE_API_KEY`. `.env.example` points it at Gemini. With no key at all, the two sample sheets still answer, and **Project Check** compares a schedule, a note, and a drawing name without a model. Press **Load sample** in that panel. A match there means the written numbers agree, not that the sheet was counted.

### Optional: the trained checker

This is the only step that needs Python. One machine can run it for the whole team. The others do not install PyTorch; they point the site at that machine.

Python 3.13, with PyTorch, Ultralytics, FastAPI, Pillow, and `python-multipart`.

```powershell
cd counting
py -3.13 -m pip install torch ultralytics fastapi uvicorn python-multipart pillow
py -3.13 -m uvicorn server:app --host 0.0.0.0 --port 8765
```

The service listens on port 8765. It has no page at the root: `GET /` returns 404. The routes are `/health`, `/detect`, and `/arbitrate`.

`/detect` receives the image and the question. It returns the total, the rectangles on a 0–1000 scale (`ymin, xmin, ymax, xmax`), and a confidence score. The weights in use are `counting/runs/window-door/weights/best.pt`. The threshold, chosen on the validation plans, is in `counting/detector_threshold.txt` (0.40).

On the other machines, add this to `STOA-eyes/.env` and restart the dev server. Use `http://127.0.0.1:8765` when the service is on the same machine.

```
DETECTOR_URL=http://<that-machine>:8765
```

If `DETECTOR_URL` is unset, the site looks for `http://127.0.0.1:8765` and keeps going when nothing is there. Without the key, a window or door count comes from the detector alone and stays marked "to check".

## What arbitration does

| Situation | Badge | What is shown |
|---|---|---|
| Windows or doors, equal totals, overlapping boxes | RELIABLE | the detector total |
| Windows or doors, totals or boxes disagree | CHECK | the disputed rectangles, clickable |
| Windows or doors, detector not running | NOT CHECKED | the vision model's answer, with a warning |
| Any other question | NOT CHECKED | the vision model's answer, with a warning |
| IFC, PDF, archive name (`_sheet_`, HABS, Finna, Europeana, Wikimedia) | OUT OF SCOPE | no count |

The same rule lives in `counting/arbitrate.py` and in `STOA-eyes/src/lib/checker.ts`. The site applies it itself, so a missing detector does not stop the answer. `detections.ts` maps the rectangles onto the canvas.

```powershell
cd counting
py -3.13 -m unittest test_checker.py
```

## The measurement

The held-out split is in `counting/eval_split.csv`: 36 plans, 64 window and door questions. It is not a block of 27 plans. The threshold is chosen on 36 other validation plans.

Rerun the report without recomputing predictions that are already cached:

```powershell
cd counting
py -3.13 compare_configs.py
```

Current result for the detector alone, threshold 0.40:

- exact plans: 4/36 (11.1%)
- exact questions: 17/64 (26.6%), including 19 off by one and 28 off by two or more

The vision-model column and the "precision when the system says it is sure" curve fill in only when `LOVABLE_API_KEY` is set. Answers are then written to `counting/cache/vision.jsonl`. The detail already computed is in `counting/comparison_report.txt`.

## The EDA

`eda/eda.ipynb` describes the Junction preview: volumes, question types (count, area, length, volume, text), languages, and example plans. It needs the `junction-dataset-preview` folder (or the zip of the same name) at the root of this repo, or in the folder from which the notebook is launched.

```powershell
pip install jupyter pandas matplotlib pillow pymupdf
jupyter notebook eda/eda.ipynb
```

PyMuPDF displays the PDFs. Without it, the notebook says so and continues with the images.

The preview and its zip are not in git: the zip is about 480 MB, and GitHub rejects a file larger than 100 MB.

## Retrain the detector

Image tiles are not versioned. They are rebuilt from the SVGs and the preview:

```powershell
cd counting
py -3.13 export_yolo.py
py -3.13 train_detector.py
```

`counting/yolo/dataset.yaml` points at the `yolo` folder. Training writes a new `runs/window-door/weights/best.pt`.

## What stays out of the repo

| File | Why |
|---|---|
| `junction-dataset-preview/` and its zip | the full preview, past the GitHub size limit |
| `counting/weights/model_best_val_loss_var.pkl` | published CubiCasa checkpoint, 199 MB, used only by `run_published.py` |
| `counting/yolo/images` and `labels` | tiles regenerated by `export_yolo.py` |
| `node_modules/`, `__pycache__/` | installed dependencies |
| `.env` | the vision model key |
