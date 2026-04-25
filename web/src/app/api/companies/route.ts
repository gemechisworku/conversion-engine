import { existsSync, readFileSync } from "fs";
import path from "path";
import { parse } from "csv-parse/sync";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type Row = Record<string, string>;

function websiteToDomain(website: string): string {
  const w = (website || "").trim();
  if (!w) return "";
  try {
    const u = new URL(w.startsWith("http") ? w : `https://${w}`);
    return u.hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function resolveCsvPath(): string {
  const fromEnv = process.env.CRUNCHBASE_DATASET_PATH?.trim();
  if (fromEnv) return path.resolve(fromEnv);
  return path.join(process.cwd(), "..", "tenacious_sales_data", "crunchbase-companies-information.csv");
}

export function GET() {
  const csvPath = resolveCsvPath();
  if (!existsSync(csvPath)) {
    return NextResponse.json(
      { companies: [], warning: "crunchbase_csv_not_found", path: csvPath },
      { status: 200 },
    );
  }
  try {
    const raw = readFileSync(csvPath, "utf-8");
    const rows = parse(raw, {
      columns: true,
      skip_empty_lines: true,
      relax_quotes: true,
      relax_column_count: true,
    }) as Row[];
    const companies = rows
      .map((row) => {
        const id = String(row.id ?? row.company_id ?? "").trim();
        const name = String(row.name ?? "").trim();
        const website = String(row.website ?? "").trim();
        if (!id || !name) return null;
        return { id, name, domain: websiteToDomain(website) };
      })
      .filter((c): c is NonNullable<typeof c> => c !== null)
      .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
    return NextResponse.json({ companies });
  } catch {
    return NextResponse.json({ companies: [], warning: "crunchbase_csv_parse_error" }, { status: 200 });
  }
}
