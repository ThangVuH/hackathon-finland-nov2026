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

## API key

Drawing questions call the AI service from the server. That call needs `LOVABLE_API_KEY`.

The site still loads without the key. Asking about a drawing then returns “The AI service isn’t configured.”

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
