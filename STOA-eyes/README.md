# Stoa Vision

AI drawing analysis for site engineers. Open a floor plan, ask a question, and check each counted item on the sheet.

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

## Counting service

Not required to open the site. Without it, window and door counts still come back from the vision model and stay marked "not checked".

To mark a count reliable, run the service that is already trained, from `counting/` at the repo root. One shared machine is enough; set `DETECTOR_URL` on the others. See the repo README. Do not reinstall a training environment just to launch the page.

## Project Check

Open **Project Check** and press **Load sample**, or upload a schedule, notes, and drawings together. The check compares quantities written in those files and pairs each space with a blueprint by file name. It does not call a model. **Match** means the written numbers agree and a sheet name matches the space. It does not mean the drawing was counted.

## API key

Drawing questions use the first key that is set: `STOA_API_KEY` (Gemini or another OpenAI-compatible model, see `.env.example`), then `OPENAI_API_KEY`, then `LOVABLE_API_KEY`.

With no key, the two sample sheets still answer locally, and a window or door count on any other drawing needs the optional detector. Those answers stay unchecked unless the detector and a vision model agree. Put the key in `.env` in this folder and restart the dev server:

```
LOVABLE_API_KEY=your-key
```

Do not commit the key.

## Built with

- TanStack Start
- TypeScript
- React
- Tailwind CSS
