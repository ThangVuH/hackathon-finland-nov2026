# Stoa Vision

A site engineer keeps one drawing in the center and checks every count on that drawing. Stoa Vision answers questions such as “How many doors?” with numbered boxes on the sheet.

## Pitch

### One line

Stoa Vision counts what is drawn on a construction sheet and puts a numbered box on each item, so the count can be checked by eye.

### The problem

On site, someone has to find the doors, windows, rooms, and columns on the plan. A bare number from a model is not enough. The engineer has to see which mark was counted.

### The product

One sheet stays in the center. Drawing Q&A sits beside it. It reads one PNG, JPG, or WebP and returns a sentence, a count, and one box per item. The boxes are numbered on the sheet.

The questions the app asks now are doors, windows, rooms, columns, and stairs. Each door or window is labeled with the room it belongs to, such as “Bedroom 1 door” or “Kitchen window”.

### A three-minute demo

1. Open the app. The apartment plan is already loaded. The header says **Drafted**.
2. Press **How many doors?**. Wait for the numbered boxes. Click a row in the list and the view moves to that door.
3. Press **How many rooms?**. Each box covers a room interior, and the label is the name printed in that room.

That is the pitch. The drawing shows its work. The count is a set of boxes, not a number floating without a source.

### What to say about the model

Drawing Q&A is one vision-language model, Gemini, looking at one image. It was not trained on this project’s drawings. Six short reading rules go out with every question. The model must count only what is drawn, skip the title block and dimension text, and return a box for each item.

The engineer remains the checker. A wrong box is visible. The product is built around that review, not around an uncheckable total.

### What not to claim

- It is not a trained detector, and it does not learn from corrections yet.
- It does not measure with a ruler. A scale on the sheet is not turned into meters.
- It does not export CAD, DXF, or a vector graph.
- It does not classify furniture against electrical symbols.
- Image redraw is not part of the demo. A free Gemini key has no image-model quota, so a sketch is counted from the original picture.

## Who it is for

Site engineers and reviewers who have a sheet open and need to see which mark was counted before they trust a number.

## Features

### Drawing Q&A

Open one drawing and ask a question. The ready questions are:

- How many doors?
- Count all windows
- How many rooms?
- Count the columns

A typed question uses the same reading rules. The answer has three parts: a sentence, a count, and a verification list. Each row is one item, with a label and a box. The box is drawn on the sheet. Hover or select a row to highlight that item.

Two sample sheets are loaded: **A-101 · 2BR Apartment** and **A-201 · Office Level 1**. Upload adds a PNG, JPG, or WebP.

With no API key, the local backend answers those two sample sheets from stored counts, so the boxes can be shown without a model. Any other picture asks for a key. The panel shows which backend is active.

Up to eight earlier turns in the same sheet are sent as text. Earlier images are not sent again.

## How an image is processed

PNG, JPG, and WebP follow the same steps. A picture is not forced into one type. Crisp black lines and pencil strokes are marked separately, and a drafted sheet with pencil on it keeps both marks.

1. The sheet opens in the center at its real pixel size. Zoom, pan, and fit sit on that view.
2. A small copy is scored twice:
   - **Drafted** — even black lines on white paper. The two sample plans get this mark.
   - **Hand sketch** — a gray patch, such as a pencil note, that is not the soft edge of a black line. On a drafted sheet this mark turns on as well. Thin gray CAD lines stay drafted only.
   - **Complicated** — a sketch, pencil on a drafted sheet, or a picture without clean drafted lines. A clean drafted sheet is not complicated.
3. The question uses one JPEG. The long side is at most 2048 px, the shape stays the same, and the compression stays high, so two door swings drawn close together do not blur into one mark. A clean drafted sheet is that JPEG of the original. A complicated sheet is sent as drawn as well: the free image models that could redraw it have no quota, and the app does not show a redraw step.
4. The server sends that JPEG, the pixel size, the question, and six reading rules to Gemini. The drafted and hand-sketch labels are not sent. The model sees the picture, not the badge.
5. Gemini returns JSON: a sentence, a count, and one box per item on a 0–1000 scale. `0,0` is the top-left of the JPEG. `1000,1000` is the bottom-right.
6. The server drops empty boxes and numbers the rest. The sheet on screen draws those boxes, so the count can be checked against the drawing.

Both marks can be on at once. A drafted sheet with pencil keeps the drafted mark and the hand-sketch mark. One mark does not cancel the other. Later steps for each mark both apply. Today those steps share the same JPEG and the same six rules. The marks are the hook for a later split, not a second model.

### No model key

Steps 1 and 2 still run. A question about a sample sheet whose name matches the apartment or the office is answered from stored sample counts. Any other picture asks for a key.

## How a count is decided

Every question sends the same six rules. They are short on purpose. The model can see only this one image, and it is told not to guess.

1. **Role.** Count and locate only what is drawn.
2. **Scan.** Read the sheet left to right, then top to bottom, including the edges. Skip the title block, the north arrow, and dimension text.
3. **Marks.** Use the legend on the sheet. Solid lines are visible edges. Dashed lines are hidden edges, not extra windows. Dimension lines, center lines, and cutting lines are not openings. A note such as CJ, EJ, or TS is a joint or a slab edge, not a door or a window. On an A sheet, count architectural doors and windows. On an S sheet, small squares on the grid are columns. A grid tag printed beside a symbol is added to the label.
4. **Elements.** A door is a leaf, a swing, a slider, or an opening. Two swings next to each other are two doors, each with its own box. A double door is one opening with two leaves and stays one door. A window is one opening drawn as thin parallel lines. A room box covers the interior, and the label uses the room name printed there. A column is the structural mark, not the grid bubble. One stair flight is one stair.
5. **Order.** Walls come first: one thick continuous run, or a hatch. A window or a door is a gap in that wall, so it is not the wall. Across the gap, two or three thin parallel lines and no swing arc is a window. An empty gap or a single thin line with a quarter-circle swing is a door. A long run of thin parallel lines in place of a thick wall is one glass wall, not a row of windows. A room is the free space enclosed by the walls. A door gap does not split one room into two. The room name is the text inside that space or just beside it.
6. **Output.** One item per instance. The box is tight on a door or a window and covers the interior of a room. `count` equals the number of items. `answer` states the count in one sentence.

There is no example image and no example answer. One Gemini call answers one question.

## What stays out

These ideas were considered and left out of the current count, so a pitch should not add them.

- **Meters.** A door width of 0.7–1.2 m needs a scale. The model is not measuring the sheet with a ruler.
- **Floors.** A hatch such as TILE, or the level printed in the title block, is not a room. Floor levels are not a question in the app.
- **Furniture and electrical symbols.** Outlets, switches, and furniture are not in the question list. Shape alone does not separate them, and the app does not run template matching.
- **A second model in front of Gemini.** Cloud Vision reads printed words. It does not know a door swing from a wall, and it needs a Google Cloud billing account. The AI Studio key does not call it.
- **Redraw before the count.** Nano Banana and the other Gemini image models are paid on this key. The free quota is zero. The app does not show a Banana message. The original sheet is what gets counted.
- **A trained classifier.** Corrections are not stored as a training set. There is no gradient-boosted model and no small network on crops.

## Run locally

You need Node.js 22 or newer and npm.

From this folder:

```sh
npm install
npm run dev
```

The dev server prints a local URL. It is usually http://localhost:8080/.

If `npm install` fails with `UNABLE_TO_VERIFY_LEAF_SIGNATURE`, Node is not using the machine certificate store. On Windows PowerShell, start it like this:

```powershell
$env:NODE_OPTIONS="--use-system-ca"
npm install
npm run dev
```

## Backend

Drawing Q&A runs on the server in this app. The key stays on the server.

The server picks one backend:

1. `STOA_API_KEY` or `OPENAI_API_KEY` sends the sheet to an OpenAI-compatible model. The free default in `.env.example` is Gemini Flash (`gemini-3.6-flash`), called through Gemini’s own `generateContent` endpoint. The image goes as inline data. The reply is JSON.
2. `LOVABLE_API_KEY` is used only when those keys are empty.
3. With no key, the local backend answers the sample sheets so the boxes and counts can be tested now.

Copy `.env.example` to `.env` when you have a key, then restart `npm run dev`. Do not commit `.env`.

`STOA_IMAGE_MODEL` is the unused redraw model name. Leave it. A free key will not return an image from it.

## Built with

- TanStack Start
- TypeScript
- React
- Tailwind CSS
