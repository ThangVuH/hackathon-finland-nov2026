import { describe, expect, it } from "vitest";

import { checkProject } from "./project-check";
import { gridsFromXlsx, unzip } from "./project-files";

describe("readProjectFiles", () => {
  it("reads an xlsx schedule and pairs Office 1 with its blueprint", async () => {
    const grids = gridsFromXlsx(await unzip(xlsxBytes()));
    const report = checkProject([{ name: "schedule.xlsx", drawing: false, grids }, { name: "A-201 Office 1.png", drawing: true }]);
    const windows = report.findings.find((finding) => finding.space === "Office 1" && finding.element === "window");
    expect(windows).toMatchObject({ status: "match", blueprint: "A-201 Office 1.png" });
    expect(windows?.quantities[0]?.quantity).toBe(4);
  });
});

function xlsxBytes(): Uint8Array {
  const shared = `<?xml version="1.0"?><sst><si><t>Space</t></si><si><t>Windows</t></si><si><t>Doors</t></si><si><t>Office 1</t></si></sst>`;
  const sheet = `<?xml version="1.0"?><worksheet><sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>
    <row r="2"><c r="A2" t="s"><v>3</v></c><c r="B2"><v>4</v></c><c r="C2"><v>2</v></c></row>
  </sheetData></worksheet>`;
  const workbook = `<?xml version="1.0"?><workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Openings" sheetId="1" r:id="rId1"/></sheets></workbook>`;
  const rels = `<?xml version="1.0"?><Relationships><Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>`;
  return storedZip([
    { name: "xl/sharedStrings.xml", data: shared },
    { name: "xl/worksheets/sheet1.xml", data: sheet },
    { name: "xl/workbook.xml", data: workbook },
    { name: "xl/_rels/workbook.xml.rels", data: rels },
  ]);
}

function storedZip(files: { name: string; data: string }[]): Uint8Array {
  const encoder = new TextEncoder();
  const parts: Uint8Array[] = [];
  const centrals: Uint8Array[] = [];
  let offset = 0;
  for (const file of files) {
    const name = encoder.encode(file.name);
    const data = encoder.encode(file.data);
    const local = concat([
      le32(0x04034b50), le16(20), le16(0), le16(0), le16(0), le16(0),
      le32(0), le32(data.length), le32(data.length), le16(name.length), le16(0),
      name, data,
    ]);
    const central = concat([
      le32(0x02014b50), le16(20), le16(20), le16(0), le16(0), le16(0), le16(0),
      le32(0), le32(data.length), le32(data.length),
      le16(name.length), le16(0), le16(0), le16(0), le16(0), le32(0), le32(offset),
      name,
    ]);
    parts.push(local);
    centrals.push(central);
    offset += local.length;
  }
  const central = concat(centrals);
  const eocd = concat([
    le32(0x06054b50), le16(0), le16(0), le16(files.length), le16(files.length),
    le32(central.length), le32(offset), le16(0),
  ]);
  return concat([...parts, central, eocd]);
}

function concat(parts: Array<Uint8Array | number[]>): Uint8Array {
  const bytes = parts.map((part) => (part instanceof Uint8Array ? part : Uint8Array.from(part)));
  const out = new Uint8Array(bytes.reduce((sum, part) => sum + part.length, 0));
  let at = 0;
  for (const part of bytes) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}

function le16(value: number): number[] {
  return [value & 255, (value >> 8) & 255];
}

function le32(value: number): number[] {
  return [value & 255, (value >> 8) & 255, (value >> 16) & 255, (value >> 24) & 255];
}
