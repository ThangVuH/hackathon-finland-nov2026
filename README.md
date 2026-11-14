# Stoa — version 1.1

A floor plan, a question, and an answer you can tell is reliable.

The front end, `STOA-eyes`, opens a plan and asks a question. It runs with Node.js and a vision-model key. The trained detector is optional. A window or door count is marked **reliable** only when its total equals the vision model's and the rectangles overlap. Otherwise the count is **to check**. Disagreed rectangles stay highlighted, and a click keeps or removes them. A dropped PDF or IFC is read by the file readers. A DWG, a DXF, or an archive sheet is refused, and no count is invented.

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

Python 3.13.5. The commands use `py -3.13`. The pinned packages are `counting/requirements.txt`.

```powershell
cd counting
py -3.13 -m pip install -r requirements.txt
py -3.13 -m uvicorn server:app --host 0.0.0.0 --port 8765
```

The service listens on port 8765. It has no page at the root: `GET /` returns 404. The routes are `/health`, `/detect`, `/arbitrate`, and `/file`. It starts from this repository alone. The preview dataset is needed only to rerun a measurement or to retrain, not to answer.

`/detect` receives the image and the question. It returns the total, the rectangles on a 0–1000 scale (`ymin, xmin, ymax, xmax`), and a confidence score. The weights in use are `counting/runs/multiclass/weights/epoch22.pt`. The live cutoffs, chosen on the validation plans before the test was read, are window 0.30, door 0.45, sink 0.60, toilet 0.45, shower 0.15, sauna stove 0.15. `counting/detector_threshold.txt` (0.40) belongs to the earlier window-and-door model and is not applied to this one.

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
| Dropped PDF or IFC | the file reader | boxes, a polygon, or a room list with GlobalId |
| DWG, DXF, or an archive name (`_sheet_`, HABS, Finna, Europeana, Wikimedia) | OUT OF SCOPE | no count |

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

## Measured limits

Counts are exact. An area is exact when it is within 2%. Kitchen is not in the detector total: on the official test, every answer is the training mode.

CubiCasa, official test, read once after the epoch and the cutoffs were frozen. The constant is the most frequent training answer, ties keeping the smaller one.

| Question | Detector | Constant |
|---|---|---|
| Windows | 5/27 | 1/27 |
| Doors | 5/19 | 0/19 |
| Toilets | 16/26 | 12/26 |
| Sinks | 10/27 | 10/27 |
| Showers and bathtubs | 4/27 | 14/27 |
| Saunas | 8/13 | 7/13 |
| All of the above | 48/139 | 44/139 |

The non-modal plans, where the answer is not the training mode, are 32/95. Showers stay under the constant. Sauna 6/6 means six plans, not a finished definition: the test definition is 12/13. The public window model also scores 5/27. Do not treat these as a clear win over that model.

Swiss, PDF inference, measured on 50 revision plans. The sentences already in the table did not move after the apostrophe and letter-code fix: labels 303/303, one room 97/98, labelled total 42/50, indoor total 37/50, apartments 50/50, doors 29/50. The three repaired sentences enter on top: "Cage d'escalier" on 9 plans, 9/9, and rooms U1.09 and U1.15, 2/2. Doors stop at the arcs. The PDF stroke equals that count on 50/50, so it is not a second measurement. Apartment area has no solver.

The 15 holdout buildings were read once, after that rehearsal, from predictions written before the answers were opened. The constant beside them is the rule already used on the 50: the most frequent answer of a sentence that repeats there, otherwise the most frequent answer of the template, and a tie keeps the smaller value. It was not refit on the 15. A baseline hit is an equal value.

| Question | 15, one read | Constant from the 50 |
|---|---|---|
| Labels | 93/93 | 34/93 |
| One room | 29/30 | 0/30 |
| Labelled total | 12/15 | 0/15 |
| Indoor total | 12/15 | 0/15 |
| Apartments | 15/15 | 4/15 |
| Doors | 8/15 | 0/15 |

One mode for every label question on the 50 is 1, which would score 24/93. The sentence rule above scores 34/93. The single modes are label 1, room area 8.98, labelled total 12.67, indoor total 34.08, apartments 1, doors 12. Apartments at 15/15 and labels at 93/93 are the reader against that constant, not a bare fraction.

IFC is a development score, with no file held out. On a dropped file the page lists each room's name, value, and GlobalId, and it shows the margin of the property chosen on that file. It does not show 215/225.

A vision-only pass is declared in `counting/vlm_alone.txt` and written call by call in `counting/vlm_alone_result.txt`. A failed call, including HTTP 429, is a missing answer. Precision and coverage use the successes only.

## Inference cost

Measured on this machine, Python 3.13.5, CPU. No vision call was made, so this is not a comparison with the vision-only pass.

| Route | LLM calls | Median latency |
|---|---|---|
| Label count | 0 | 0.036 s to read the plan, then 0.003 s |
| Room area, labelled total, indoor total | 0 | the same plan read, then under 0.001 s |
| Apartment count | 0 | included in the label read |
| PDF doors | 0 | 0.009 s for the strokes |
| Dropped IFC | 0 | 0.516 s over 5 bench files |
| Sinks, toilets, showers, saunas | 0 | the detector, below |
| Windows or doors on pixels | 0 without a key; 1 vision call when a key is set | the detector, and the badge stays unchecked without the key |

The detector loads in 4.2 s the first time, including the weights. After that, on 5 CubiCasa preview plans (median about 333 000 pixels), the median is 0.070 s of wall time and 0.516 s of process time per plan. Process time can exceed wall time because the library uses more than one thread. The detail is `counting/cost_table.txt`.

## Not measured

- The vision-only pass, and the precision of the agreement badge: not measured. All 35 calls were HTTP 429.
- Swiss windows, toilets, washbasins, bathtubs, and apartment area: no solver. The badge stays unverified.
- IFC: a development score, with no file held out.
- CubiCasa: 48/139 against 44 for the constant.

## Protocol

The measurement was frozen in this order, on `version-1-1`:

| Commit | What was frozen |
|---|---|
| `0cf3e01` | the Swiss split and the door candidates |
| `29bb6cd` | the area fallback and every door rule tried on the 50 |
| `f3fe5b2` | apostrophes and letter room codes, before the 15 were read |
| `b41e38f` | the measured limits, the one reading of the 15, and the cached demo routes |

`v1.1-freeze` points at `b41e38f`.

## What to say

Where the file is structured, the answer is exact and the drawing shows where it came from. Where there are only pixels, exact counting stays hard, 48/139 against 44 for the constant, and the badge says so.

- Swiss: measured on 50 revision plans, 15 read once.
- IFC: a development score, with no file held out.
- CubiCasa: 48/139, against 44 for the constant, with the counts above.

## Four scenes, about three minutes

1. Swiss sample, "How many rooms labelled 'Zimmer' ?". Twelve text boxes, answer 12.
2. The same plan, the area of room 2.10. The polygon is drawn. The warning says the written scale and the printed areas agree.
3. A dropped IFC. One line per room: name, value, GlobalId, and the margin of the chosen property.
4. A CubiCasa plan, window boxes, the line "5 exact on 27", and the sentence that an exact count on pixels alone stays hard.

Five of the eight preregistered foreign routes were not returned by the model. The page marks every one of them "Route en cache". The three that did come back are a Swedish door question, a Dutch apartment question, and a Polish question with no template. Do not present a cached route as a live classification.

## Data and licence

Room and opening labels used to train the detector come from CubiCasa5K. That dataset is CC BY-NC-SA. The trained detector is a derivative of those labels, so it is not for commercial use. Credit CubiCasa5K when the detector or its counts are shown.

## The four criteria

- Accuracy: the tables above, each family next to its constant. Swiss is measured on 50 revision plans, with 15 read once. CubiCasa is 48/139 against 44. IFC is a development score, with no file held out.
- A human can check: the page draws the text boxes, the polygon, or the room list with GlobalId. Each template carries its measured sentence. The limits in "Not measured" are part of that check.
- Creativity: a question is routed to the structured file when the file has the answer. The protocol above was frozen before the reading. When the written scale and the printed areas disagree, the written scale is the one used, and the page says so.
- Cost: the table in "Inference cost". Recognized templates make no model call.

## Submission

Junction 2026, final submissions Sunday 15 November 2026 at 10:00, on the schedule published as UTC+02:00, through the Junction platform. Submissions opened Saturday 14 November at 12:00. The public challenge page does not say that a video or a slide deck is required. The form itself is behind the platform login, so those two fields are not confirmed here. Judging on the Stoa page: accuracy 25%, a human can verify the reasoning 25%, creativity 25%, low inference cost 25%.
