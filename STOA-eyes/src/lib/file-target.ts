export type NamedFile = { id: string; name: string };

export type DrawingSelection =
  | { kind: "files"; files: NamedFile[] }
  | { kind: "missing"; reply: string }
  | { kind: "choose"; files: NamedFile[] };

const GENERIC = new Set([
  "png",
  "jpg",
  "jpeg",
  "webp",
  "pdf",
  "img",
  "image",
  "scan",
  "plan",
  "plans",
  "floor",
  "floors",
  "drawing",
  "drawings",
  "sheet",
  "sheets",
  "blueprint",
  "blueprints",
  "file",
  "files",
  "copy",
  "level",
  "page",
  "final",
  "rev",
  "revision",
  "door",
  "doors",
  "window",
  "windows",
  "room",
  "rooms",
  "column",
  "columns",
  "stair",
  "stairs",
  "wall",
  "walls",
  "opening",
  "openings",
  "grid",
  "grids",
  "bedroom",
  "bedrooms",
  "kitchen",
  "kitchens",
  "bath",
  "baths",
  "hallway",
  "hallways",
]);

const EVERY_FILE =
  /\b(?:all|every|each|both)\b[\w\s]{0,24}\b(?:files?|drawings?|sheets?|plans?|blueprints?)\b|\b(?:files?|drawings?|sheets?|plans?|blueprints?)\b[\w\s]{0,12}\b(?:all|every|each)\b/i;

/** Pieces of a file name that a question can cite, such as 1732 or apartment. */
export function nameKeys(fileName: string): string[] {
  const stem = fileName.replace(/\.[^.]+$/, "");
  const parts = stem.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  return parts.filter((part) => {
    if (GENERIC.has(part)) return false;
    if (/\d/.test(part)) return part.length >= 3;
    return part.length >= 4;
  });
}

function mentions(question: string, key: string): boolean {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?:^|[^a-z0-9])${escaped}(?:[^a-z0-9]|$)`, "i").test(question);
}

/**
 * A question reads only the drawings it names.
 * With several drawings and no name, it asks which one, or all of them.
 * One loaded drawing is read directly.
 */
export function selectDrawingTargets(question: string, files: NamedFile[], _activeId: string | null): DrawingSelection {
  const named = files.filter((file) => nameKeys(file.name).some((key) => mentions(question, key)));
  if (named.length > 0) return { kind: "files", files: named };

  if (EVERY_FILE.test(question)) return { kind: "files", files };

  const stray = [...question.matchAll(/\b\d{3,}\b/g)].map((match) => match[0]);
  const unique = [...new Set(stray)];
  if (unique.length > 0) {
    const quoted = unique.join(", ");
    const loaded = files.map((file) => file.name).join(", ");
    const reply = loaded
      ? `No loaded drawing matches ${quoted}. The files here are ${loaded}.`
      : `No loaded drawing matches ${quoted}.`;
    return { kind: "missing", reply };
  }

  if (files.length > 1) return { kind: "choose", files };
  return { kind: "files", files: files[0] ? [files[0]] : [] };
}
