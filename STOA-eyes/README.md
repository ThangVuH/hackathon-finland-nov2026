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

## API key

Questions call the vision model from the server. That call needs `LOVABLE_API_KEY`.

The site still loads without the key. A window or door count then needs the optional detector, and is marked unchecked. Any other question returns “The AI service isn’t configured.”

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
