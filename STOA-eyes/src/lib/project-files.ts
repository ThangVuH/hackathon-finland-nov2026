/** Browser readers for project files. Text, CSV, XLSX, DOCX, and PDF text only. */

import { type ProjectDocument } from "./project-check";

const IMAGE = /\.(png|jpe?g|webp|gif)$/i;
const SHEET_NAME = /(plan|drawing|blueprint|sheet|\b[a-z]{1,3}-\d{2,4}\b)/i;

export async function readProjectFiles(files: File[]): Promise<ProjectDocument[]> {
  const docs: ProjectDocument[] = [];
  for (const file of files) {
    docs.push(await readOne(file));
  }
  return docs;
}

async function readOne(file: File): Promise<ProjectDocument> {
  const name = file.name;
  if (IMAGE.test(name) || file.type.startsWith("image/")) return { name, drawing: true };

  try {
    if (/\.csv$/i.test(name) || file.type === "text/csv") {
      return { name, drawing: false, grids: [{ sheet: "", rows: parseDelimited(await fileText(file)) }] };
    }
    if (/\.(txt|md|markdown)$/i.test(name) || file.type.startsWith("text/")) {
      return { name, drawing: false, text: await fileText(file) };
    }
    if (/\.xlsx$/i.test(name)) {
      const grids = gridsFromXlsx(await unzip(await fileBytes(file)));
      return { name, drawing: false, grids };
    }
    if (/\.docx$/i.test(name)) {
      const entries = await unzip(await fileBytes(file));
      const xml = entries.get("word/document.xml");
      const text = xml ? stripXml(new TextDecoder().decode(xml)).replace(/\s+/g, " ").trim() : "";
      return text
        ? { name, drawing: false, text }
        : { name, drawing: false, note: "No readable text in this document." };
    }
    if (/\.pdf$/i.test(name) || file.type === "application/pdf") {
      const text = await extractPdfText(await fileBytes(file));
      const drawing = SHEET_NAME.test(name) || text.trim().length < 400;
      return text.trim()
        ? { name, drawing, text }
        : { name, drawing: true, note: "No readable text in this PDF. It is kept as a blueprint." };
    }
  } catch (error) {
    console.error("[stoa] project file", name, error);
    return { name, drawing: false, note: "This file could not be read. Use CSV, XLSX, TXT, PDF, or DOCX." };
  }

  return { name, drawing: false, note: "This file type is not read yet. Use CSV, XLSX, TXT, PDF, DOCX, or an image." };
}

async function fileText(file: Blob): Promise<string> {
  return await new Response(file).text();
}

async function fileBytes(file: Blob): Promise<Uint8Array> {
  return new Uint8Array(await new Response(file).arrayBuffer());
}

export function parseDelimited(text: string): string[][] {
  const source = text.replace(/^\uFEFF/, "");
  const first = source.split(/\r?\n/, 1)[0] ?? "";
  const commas = (first.match(/,/g) ?? []).length;
  const tabs = (first.match(/\t/g) ?? []).length;
  const semis = (first.match(/;/g) ?? []).length;
  const delimiter = tabs > commas && tabs >= semis ? "\t" : semis > commas ? ";" : ",";

  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < source.length; i++) {
    const char = source[i]!;
    if (quoted) {
      if (char === '"') {
        if (source[i + 1] === '"') {
          cell += '"';
          i++;
        } else quoted = false;
      } else cell += char;
      continue;
    }
    if (char === '"') {
      quoted = true;
      continue;
    }
    if (char === delimiter) {
      row.push(cell.trim());
      cell = "";
      continue;
    }
    if (char === "\n") {
      row.push(cell.trim());
      rows.push(row);
      row = [];
      cell = "";
      continue;
    }
    if (char !== "\r") cell += char;
  }
  if (cell.length || row.length) {
    row.push(cell.trim());
    rows.push(row);
  }
  return rows.filter((line) => line.some(Boolean));
}

export async function unzip(bytes: Uint8Array): Promise<Map<string, Uint8Array>> {
  const eocd = findEocd(bytes);
  if (eocd < 0) throw new Error("Not a zip file");
  const count = u16(bytes, eocd + 10);
  let offset = u32(bytes, eocd + 16);
  const out = new Map<string, Uint8Array>();
  for (let i = 0; i < count; i++) {
    if (u32(bytes, offset) !== 0x02014b50) break;
    const method = u16(bytes, offset + 10);
    const compressed = u32(bytes, offset + 20);
    const nameLen = u16(bytes, offset + 28);
    const extraLen = u16(bytes, offset + 30);
    const commentLen = u16(bytes, offset + 32);
    const local = u32(bytes, offset + 42);
    const name = new TextDecoder().decode(bytes.subarray(offset + 46, offset + 46 + nameLen));
    const localNameLen = u16(bytes, local + 26);
    const localExtraLen = u16(bytes, local + 28);
    const start = local + 30 + localNameLen + localExtraLen;
    const slice = bytes.subarray(start, start + compressed);
    out.set(name, method === 0 ? slice : await inflateRaw(slice));
    offset += 46 + nameLen + extraLen + commentLen;
  }
  return out;
}

export function gridsFromXlsx(entries: Map<string, Uint8Array>): { sheet: string; rows: string[][] }[] {
  const decoder = new TextDecoder();
  const shared = sharedStrings(entries.get("xl/sharedStrings.xml"));
  const workbook = decoder.decode(entries.get("xl/workbook.xml") ?? new Uint8Array());
  const rels = decoder.decode(entries.get("xl/_rels/workbook.xml.rels") ?? new Uint8Array());
  const sheets = [...workbook.matchAll(/<sheet\b[^>]*name="([^"]*)"[^>]*r:id="([^"]+)"/g)];
  const grids: { sheet: string; rows: string[][] }[] = [];
  const targets = sheets.length
    ? sheets.map((match) => {
        const id = match[2] ?? "";
        const rel = new RegExp(`Id="${id}"[^>]*Target="([^"]+)"`).exec(rels);
        const target = rel?.[1] ?? "";
        return { sheet: decodeXml(match[1] ?? "Sheet"), path: target.startsWith("xl/") ? target : `xl/${target.replace(/^\//, "")}` };
      })
    : [...entries.keys()]
        .filter((path) => /^xl\/worksheets\/sheet\d+\.xml$/.test(path))
        .map((path) => ({ sheet: path, path }));

  for (const target of targets) {
    const xml = entries.get(target.path);
    if (!xml) continue;
    grids.push({ sheet: target.sheet, rows: sheetRows(decoder.decode(xml), shared) });
  }
  return grids;
}

function sharedStrings(bytes: Uint8Array | undefined): string[] {
  if (!bytes) return [];
  const xml = new TextDecoder().decode(bytes);
  const items: string[] = [];
  for (const si of xml.matchAll(/<si\b[^>]*>([\s\S]*?)<\/si>/g)) {
    const parts = [...(si[1] ?? "").matchAll(/<t\b[^>]*>([\s\S]*?)<\/t>/g)].map((match) => decodeXml(match[1] ?? ""));
    items.push(parts.join(""));
  }
  return items;
}

function sheetRows(xml: string, shared: string[]): string[][] {
  const rows = new Map<number, string[]>();
  for (const cell of xml.matchAll(/<c\b([^>]*)>([\s\S]*?)<\/c>/g)) {
    const attrs = cell[1] ?? "";
    const body = cell[2] ?? "";
    const ref = /r="([A-Z]+\d+)"/.exec(attrs)?.[1] ?? "A1";
    const type = /t="([^"]+)"/.exec(attrs)?.[1] ?? "";
    const raw = /<v>([\s\S]*?)<\/v>/.exec(body)?.[1] ?? /<t\b[^>]*>([\s\S]*?)<\/t>/.exec(body)?.[1] ?? "";
    const value = type === "s" ? (shared[Number(raw)] ?? "") : decodeXml(raw);
    const col = colIndex(ref);
    const rowIndex = Number(ref.match(/\d+/)?.[0] ?? 1) - 1;
    const row = rows.get(rowIndex) ?? [];
    row[col] = value;
    rows.set(rowIndex, row);
  }
  return [...rows.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, row]) => Array.from({ length: row.length }, (_, index) => row[index] ?? ""));
}

async function extractPdfText(bytes: Uint8Array): Promise<string> {
  const parts: string[] = [];
  const latin = new TextDecoder("latin1").decode(bytes);
  parts.push(pdfLiterals(latin));
  const streams = pdfStreams(bytes);
  for (const stream of streams) {
    try {
      const inflated = await inflateZlib(stream);
      parts.push(pdfLiterals(new TextDecoder("latin1").decode(inflated)));
    } catch {
      parts.push(pdfLiterals(new TextDecoder("latin1").decode(stream)));
    }
  }
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

function pdfLiterals(content: string): string {
  const bits: string[] = [];
  const re = /\((?:\\.|[^\\)])*\)/g;
  for (const match of content.matchAll(re)) {
    const raw = match[0].slice(1, -1);
    const text = unescapePdf(raw).replace(/\s+/g, " ").trim();
    if (text.length > 1 && /[A-Za-z]/.test(text)) bits.push(text);
  }
  return bits.join(" ");
}

function unescapePdf(value: string): string {
  return value.replace(/\\([nrtbf()\\]|[0-7]{1,3})/g, (_, code: string) => {
    if (code === "n") return "\n";
    if (code === "r") return "\r";
    if (code === "t") return "\t";
    if (code === "b") return "\b";
    if (code === "f") return "\f";
    if (code === "(" || code === ")" || code === "\\") return code;
    return String.fromCharCode(parseInt(code, 8));
  });
}

function pdfStreams(bytes: Uint8Array): Uint8Array[] {
  const marker = ascii("stream");
  const end = ascii("endstream");
  const out: Uint8Array[] = [];
  let from = 0;
  while (from < bytes.length) {
    const at = indexOfBytes(bytes, marker, from);
    if (at < 0) break;
    let start = at + marker.length;
    if (bytes[start] === 13) start++;
    if (bytes[start] === 10) start++;
    const stop = indexOfBytes(bytes, end, start);
    if (stop < 0) break;
    out.push(bytes.subarray(start, stop));
    from = stop + end.length;
  }
  return out;
}

function findEocd(bytes: Uint8Array): number {
  const min = Math.max(0, bytes.length - 22 - 65535);
  for (let i = bytes.length - 22; i >= min; i--) {
    if (u32(bytes, i) === 0x06054b50) return i;
  }
  return -1;
}

async function inflateRaw(bytes: Uint8Array): Promise<Uint8Array> {
  return inflate(bytes, "deflate-raw");
}

async function inflateZlib(bytes: Uint8Array): Promise<Uint8Array> {
  return inflate(bytes, "deflate");
}

async function inflate(bytes: Uint8Array, format: "deflate" | "deflate-raw"): Promise<Uint8Array> {
  const copy = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
  const stream = new Blob([copy]).stream().pipeThrough(new DecompressionStream(format));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

function colIndex(ref: string): number {
  const letters = ref.match(/[A-Z]+/)?.[0] ?? "A";
  let n = 0;
  for (const char of letters) n = n * 26 + (char.charCodeAt(0) - 64);
  return n - 1;
}

function stripXml(xml: string): string {
  return decodeXml(xml.replace(/<[^>]+>/g, " "));
}

function decodeXml(value: string): string {
  return value
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, n: string) => String.fromCharCode(Number(n)))
    .replace(/&amp;/g, "&");
}

function u16(bytes: Uint8Array, offset: number): number {
  return (bytes[offset] ?? 0) | ((bytes[offset + 1] ?? 0) << 8);
}

function u32(bytes: Uint8Array, offset: number): number {
  return ((bytes[offset] ?? 0) | ((bytes[offset + 1] ?? 0) << 8) | ((bytes[offset + 2] ?? 0) << 16) | ((bytes[offset + 3] ?? 0) << 24)) >>> 0;
}

function ascii(value: string): Uint8Array {
  return Uint8Array.from(value, (char) => char.charCodeAt(0));
}

function indexOfBytes(haystack: Uint8Array, needle: Uint8Array, from: number): number {
  outer: for (let i = from; i <= haystack.length - needle.length; i++) {
    for (let j = 0; j < needle.length; j++) {
      if (haystack[i + j] !== needle[j]) continue outer;
    }
    return i;
  }
  return -1;
}
