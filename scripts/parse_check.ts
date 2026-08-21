// Self-check for the DDL parser: parse backend/init.sql (canonical schema) and
// print a summary so the derived `TABLES` can be inspected / validated.
// Run with: npx tsx scripts/parse_check.ts   (or: npm run schema:parse)
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { parseDdl } from '../src/schema/parseDdl';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ddl = readFileSync(resolve(__dirname, '../backend/init.sql'), 'utf8');

const tables = parseDdl(ddl);
console.log(`Parsed ${tables.length} tables from backend/init.sql\n`);

const duplicateNames = tables.map((t) => t.name);
const unique = new Set(duplicateNames);
if (unique.size !== tables.length) {
  console.error('ERROR: duplicate table names parsed');
  process.exit(1);
}

for (const t of tables) {
  const rel = t.relations.length
    ? t.relations.map((r) => `${r.fromColumn}->${r.toTable}.${r.toColumn}:${r.onDelete}`).join(', ')
    : 'none';
  const idx = t.indexes.length ? t.indexes.join('; ') : 'none';
  console.log(`  ${t.name.padEnd(24)} cols=${String(t.columns.length).padStart(2)}  indexes=[${idx}]  rel=[${rel}]`);
  for (const c of t.columns) {
    console.log(`      - ${c.name.padEnd(22)} ${c.type.padEnd(14)} ${c.constraints}${c.defaultValue ? `  DEFAULT ${c.defaultValue}` : ''}`);
  }
}

// Quick invariants a drift regression would violate.
const totalColumns = tables.reduce((n, t) => n + t.columns.length, 0);
console.log(`\nTotal columns parsed: ${totalColumns}`);
