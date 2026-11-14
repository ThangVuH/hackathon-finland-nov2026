# Stoa Vision

A workspace for site engineers. One sheet stays in the center. Two features sit beside it.

## Features

### Drawing Q&A

Open one drawing and ask a question, such as “How many doors?”. The answer comes back with numbered boxes on the sheet, so each counted item can be checked.

Sample sheets are already loaded: a 2-bedroom apartment and an office level. You can also upload a PNG, JPG, or WebP.

With no API key, the local backend answers the two sample sheets (the apartment and the office level). Other drawings need a model key. The panel shows which backend is active.

### Project Check

Upload a project and the check runs on its own. It reads schedules, notes, specifications, and drawings in the browser, then writes an executive summary.

It compares quantities written in the files, such as “Office 1 has 4 windows,” and pairs each space with a blueprint by the file name. Each claim is marked:

- **Match** — the written numbers agree, and a blueprint for that space is in the project.
- **Conflict** — two files give different numbers for the same space.
- **No sheet** — a quantity was found, and no blueprint name matches that space.

Click a file name under **Files** to open it: a schedule as a table, a note as text, or a blueprint on the sheet.

Accepted uploads: PNG, JPG, WebP, PDF, XLSX, CSV, TXT, MD, and DOCX. This check does not call the AI service.

A sample set is in `sample-project/`. In the app, open **Project Check** and press **Load sample**. The schedule says Office 1 has 4 windows, the meeting note says 3, and `A-201 Office 1.jpg` is the matching sheet. Kitchen has counts and no blueprint.

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

Drawing Q&A runs on the server in this app. Project Check does not call it.

The server picks one backend:

1. `STOA_API_KEY` or `OPENAI_API_KEY` sends the sheet to an OpenAI-compatible model. The free default in `.env.example` is Gemini Flash (`gemini-3.6-flash`).
2. `LOVABLE_API_KEY` is used only when those keys are empty.
3. With no key, the local backend answers the sample sheets so the boxes and counts can be tested now.

Copy `.env.example` to `.env` when you have a key, then restart `npm run dev`. Do not commit `.env`.

## Built with

- TanStack Start
- TypeScript
- React
- Tailwind CSS
