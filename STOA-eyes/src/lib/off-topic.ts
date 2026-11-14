const WORK =
  "Greetings. Let's get back to work. We count doors, windows, rooms, and columns on your drawings. What do you want to check?";

const ON_DRAWING =
  /\b(doors?|windows?|rooms?|columns?|stairs?|walls?|openings?|sheets?|plans?|blue\s*prints?|drawings?|grids?|floors?|bedrooms?|kitchens?|baths?|hallways?|objects?)\b/i;

const ON_TASK = /\b(how many|how much|count|number of|where|which|opposite|beside|between|next to|locate|find)\b/i;

const ON_ITEM = /(?:#\s*\d|\b(?:door|window|room|column|stair)\s*#?\s*\d|\b\d(?:st|nd|rd|th)\b)/i;

const ON_READING =
  /\b(summarize|summary|describe|description|explain|overview|identify|list|information|details?|tell me about|show me|give me)\b/i;

const ON_SHEET = /\b\d{3,}\b/;

/** "this image" names the open sheet the same way "image 7513" names a file. */
const ON_PICTURE = /\b(?:images?|pictures?|photos?|scans?)\b|\b(?:this|the|current)\s+(?:one|sheet|plan|drawing|file|blueprint)\b/i;

/** A question outside the drawings gets a fixed reply and is not sent to the model. */
export function offTopicReply(question: string): string | null {
  const text = question.trim();
  if (!text) return null;
  if (ON_DRAWING.test(text) || ON_TASK.test(text) || ON_ITEM.test(text)) return null;
  if (ON_READING.test(text) && (ON_SHEET.test(text) || ON_PICTURE.test(text))) return null;
  return WORK;
}
