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

Window and door counts are checked by the trained detector before the page trusts them. From `stoa-preview/counting`:

```sh
py -3.13 -m uvicorn server:app --port 8765
```

The page calls that service from the server. Set `DETECTOR_URL` if it is not on port 8765.

A count is marked reliable only when this detector and the vision model report the same total and their boxes overlap. Otherwise the disagreed boxes stay highlighted, and a click keeps or drops one. IFC files, PDF sheets and archive scans are refused.

## API key

Questions call the vision model from the server. That call needs `LOVABLE_API_KEY`.

The site still loads without the key. A window or door count then comes from the detector only, and is marked unchecked. Any other question returns “The AI service isn’t configured.”

Where the key comes from, and how we share it, is still to be decided. When we have one, put it in `.env` in this folder and restart the dev server:

```
LOVABLE_API_KEY=your-key
```

Do not commit the key.

## Built with

- TanStack Start
- TypeScript
- React
- Tailwind CSS
