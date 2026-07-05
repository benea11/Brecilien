import type { DectNode } from "./types";

export const CSV_IMPORT_DEFAULT_HEIGHT_M = 5.0;

export interface CsvImportResult {
  nodes: DectNode[];
  skipped: number;
}

/** RFC4136-ish tokenizer: supports either delimiter, "-quoted fields (with
 * "" as an escaped quote) and fields that embed the delimiter or newlines,
 * which the sample "Geo Shape" GeoJSON column relies on. */
function parseRows(text: string, delimiter: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += c;
      }
      continue;
    }
    if (c === '"') {
      inQuotes = true;
    } else if (c === delimiter) {
      row.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      field = "";
      rows.push(row);
      row = [];
    } else {
      field += c;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((r) => r.some((f) => f.trim().length > 0));
}

function detectDelimiter(headerLine: string): string {
  return headerLine.includes(";") ? ";" : ",";
}

function findCol(headers: string[], patterns: RegExp[]): number {
  for (const re of patterns) {
    const idx = headers.findIndex((h) => re.test(h));
    if (idx >= 0) return idx;
  }
  return -1;
}

/** Parses a CSV export of node locations into DectNodes with generic,
 * auto-numbered ids and a generic default mount height -- CSV rows carry no
 * role/type, matching manual placement: role is only ever decided by the
 * simulation engine. Understands both a combined "Geo Point" column
 * ("lat, lon" in one field, as opendatasoft-style exports use) and separate
 * lat/lon columns, and tolerates either comma or semicolon delimiters. */
export function parseNodesCsv(text: string, existingIds: Set<string>, startIndex: number): CsvImportResult {
  const stripped = text.replace(/^﻿/, "");
  const firstLine = stripped.slice(0, stripped.indexOf("\n") + 1 || stripped.length);
  const delimiter = detectDelimiter(firstLine);
  const rows = parseRows(stripped, delimiter);
  if (rows.length < 2) return { nodes: [], skipped: 0 };

  const headers = rows[0].map((h) => h.trim().toLowerCase());
  const geoPointIdx = findCol(headers, [/^geo\s*point$/, /geopoint/]);
  const latIdx = findCol(headers, [/^lat(itude)?$/]);
  const lonIdx = findCol(headers, [/^lon(gitude)?$/, /^lng$/]);
  const idIdx = findCol(headers, [/^id$/, /^name$/, /^nom$/, /^label$/]);
  const heightIdx = findCol(headers, [/^h$/, /^height/, /^hauteur/, /^altitude/, /^elevation/, /^mount/, /^mast/]);

  const nodes: DectNode[] = [];
  let skipped = 0;
  let n = startIndex;
  const usedIds = new Set(existingIds);

  for (const cells of rows.slice(1)) {
    let lat: number | null = null;
    let lon: number | null = null;

    if (geoPointIdx >= 0 && cells[geoPointIdx]?.trim()) {
      const parts = cells[geoPointIdx].split(",").map((p) => parseFloat(p.trim()));
      if (parts.length === 2 && parts.every((p) => !Number.isNaN(p))) [lat, lon] = parts;
    } else if (latIdx >= 0 && lonIdx >= 0) {
      const a = parseFloat(cells[latIdx]);
      const b = parseFloat(cells[lonIdx]);
      if (!Number.isNaN(a) && !Number.isNaN(b)) [lat, lon] = [a, b];
    }

    if (lat == null || lon == null || Number.isNaN(lat) || Number.isNaN(lon)) {
      skipped++;
      continue;
    }

    const h = heightIdx >= 0 ? parseFloat(cells[heightIdx]) : NaN;

    let id = idIdx >= 0 ? cells[idIdx]?.trim() : "";
    if (!id || usedIds.has(id)) {
      do {
        id = `N-${String(n).padStart(3, "0")}`;
        n++;
      } while (usedIds.has(id));
    }
    usedIds.add(id);

    nodes.push({ id, lat, lon, h: Number.isNaN(h) ? CSV_IMPORT_DEFAULT_HEIGHT_M : h });
  }

  return { nodes, skipped };
}
