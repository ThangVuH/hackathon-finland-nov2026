# BluePrintEYE - Junction 2026, Finland

## The challenge

Site engineers spend hours looking for information on construction drawings. A general-purpose model often fails on a dense technical sheet, and a bare number is not enough: the answer has to be right, and a person has to see where it came from in a few seconds.

BluePrintEYE answers natural-language questions about real drawings. The count is a sentence plus a numbered box on each mark, so the sheet itself is the check.

## What we focus on

Floor plans as images: PNG, JPG, or WebP. The questions are the ones an engineer asks on a plan: how many doors, windows, rooms, columns, or stairs, where they sit, a short overview of the sheet, and a follow-up such as whether one door faces another...

Several drawings can be open at once. A name or a sheet number in the question goes to that file. A general question, such as “How many doors?”, asks which drawing to read, or all of them. Each answer starts with the file name.

## How it works

The model is one piece. The rest is there so a newer model does not replace the product.

1. **Classify the sheet.** A small computer-vision pass marks clean drafted linework against pencil or a messy scan. A clean sheet is sent as drawn. A complicated sheet is sent to an image model to redraw as a plain plan with the same walls, openings, and room names. The count uses that redraw when it comes back. When the image model is missing or out of quota, the original sheet is counted.
2. **Classify the question, then stack short prompts.** Six shared rules go out every time: how to scan, how to read the legend, and how to tell a door from a window from a room. A count uses those six. A summary and a follow-up each add one more prompt. One call reads one sheet. If that model is busy, the same question is tried again, then on the next Flash model.
3. **Put the answer on the drawing.** Every item comes back as a box on a 0–1000 grid of the image. Doors, windows, rooms, columns, and stairs are numbered on their own. Drag a box, pull a corner, delete a wrong one, or add a miss. The list and the numbers follow the boxes. The sentence stays so you can compare it with the sheet.

## Run

Node.js 22 or newer.

```sh
npm install
cp .env.example .env
npm run dev
```

Put a Gemini key in `STOA_API_KEY` (https://aistudio.google.com/apikey), keep `STOA_MODEL=gemini-3.6-flash`, then restart the dev server. Open http://localhost:8080/, add drawings, and ask.

On Windows, if `npm install` fails with `UNABLE_TO_VERIFY_LEAF_SIGNATURE`:

```powershell
$env:NODE_OPTIONS="--use-system-ca"
npm install
npm run dev
```

The key stays on the server. Do not commit `.env`.

## Deploy

This is a Node server, so Streamlit and GitHub Pages cannot run it. Push this repo to GitHub, then host `STOA-eyes` on Render. The dataset folder and the zip stay out: git ignores both, and Render is pointed only at `STOA-eyes`.

1. Push the repo to GitHub. Leave `.env` uncommitted.
2. On [Render](https://render.com), create a Blueprint from the repo. `render.yaml` is already at the root.
3. When Render asks for `STOA_API_KEY`, paste the Gemini key. The other model settings are already in the blueprint.
4. Open the URL Render prints. Add a PNG, JPG, or WebP and ask.

The same image runs anywhere else with Docker, from `STOA-eyes`:

```sh
docker build -t blueprinteye .
docker run --rm -p 8080:8080 -e STOA_API_KEY=your-key -e STOA_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai/ -e STOA_MODEL=gemini-3.6-flash blueprinteye
```

A count can take up to two minutes. Use a host that allows a request that long.
