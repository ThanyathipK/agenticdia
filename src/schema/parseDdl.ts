// ============================================================================
// parseDdl.ts — lightweight, dependency-free parser for the Postgres DDL used
// by this repo (backend/init.sql).
//
// Why this exists: it derives the table/column/index/relation structure
// directly from the real DDL, so tooling (see `scripts/parse_check.ts`,
// run via `npm run schema:parse`) can validate the parsed structure against
// backend/init.sql instead of maintaining a hand-written copy that could
// drift from what the backend provisions.
//
// Scoped conventions (matching init.sql):
//   - `CREATE TABLE <name> ( <one column per line> );`
//   - `CREATE INDEX <name> ON <table>(<cols>);`
//   - `ALTER TABLE <table> ADD CONSTRAINT <name> UNIQUE (<cols>);`
//   - end-of-line `-- ...` comments are stripped (safe: no string literal here
//     contains `--`).
// Non-table statements (CREATE EXTENSION / FUNCTION / TRIGGER) are ignored.
// ============================================================================

import type { ParsedColumn, ParsedRelation, ParsedTableSchema } from './types';

/** Strip `-- ...` end-of-line comments (plus CR characters). */
function stripLineComments(sql: string): string {
  return sql
    .split(/\r?\n/)
    .map((line) => {
      const idx = line.indexOf('--');
      return idx === -1 ? line : line.slice(0, idx);
    })
    .join('\n');
}

/**
 * Parse a single column-definition line into its structural parts.
 * Returns `null` for blank lines and table-level constraint lines.
 */
function parseColumnLine(
  line: string,
): { column: ParsedColumn; relation?: ParsedRelation } | null {
  const work = line.trim().replace(/,$/, '').trim();
  if (!work) return null;

  // Table-level constraint lines (not single-column definitions).
  if (/^(PRIMARY KEY|UNIQUE|CONSTRAINT|CHECK|FOREIGN KEY)\b/i.test(work)) return null;

  const firstSpace = work.indexOf(' ');
  if (firstSpace === -1) return null;
  const name = work.slice(0, firstSpace);
  const rest = work.slice(firstSpace + 1).trim();

  // The column type is the next token (e.g. `VARCHAR(50)`, `UUID`, `JSONB`).
  const typeSpace = rest.indexOf(' ');
  const type = typeSpace === -1 ? rest : rest.slice(0, typeSpace);
  const expr = (typeSpace === -1 ? '' : rest.slice(typeSpace + 1)).trim();

  // `DEFAULT <expr>` is pulled out into its own field.
  let defaultValue: string | undefined;
  let remainder = expr;
  const defaultMatch = /\bDEFAULT\s+(.+)$/i.exec(expr);
  if (defaultMatch) {
    defaultValue = defaultMatch[1].replace(/,\s*$/, '').trim();
    remainder = expr.slice(0, defaultMatch.index).trim();
  }

  const pkey = /\bPRIMARY\s+KEY\b/i.test(remainder);
  const unique = /\bUNIQUE\b/i.test(remainder);
  const notNull = /\bNOT\s+NULL\b/i.test(remainder);

  // Foreign key + its referential action.
  const fkMatch = /\bREFERENCES\s+([A-Za-z_]\w*)\s*\(\s*([A-Za-z_]\w*)\s*\)/i.exec(remainder);
  let relation: ParsedRelation | undefined;
  if (fkMatch) {
    const odMatch = /\bON\s+DELETE\s+(.+)$/i.exec(remainder);
    const onDelete = odMatch ? odMatch[1].trim() : 'NONE';
    relation = {
      fromColumn: name,
      toTable: fkMatch[1],
      toColumn: fkMatch[2],
      onDelete: onDelete === 'CASCADE' || onDelete === 'RESTRICT' || onDelete === 'SET NULL' ? onDelete : 'NONE',
    };
  }

  // Rebuild `constraints` in the project's established convention:
  //   PRIMARY KEY | [UNIQUE] [NOT NULL] / NULL  [+ REFERENCES tbl(col)]
  let constraints: string;
  if (pkey) {
    constraints = 'PRIMARY KEY';
  } else {
    const flags: string[] = [];
    if (unique) flags.push('UNIQUE');
    if (notNull) flags.push('NOT NULL');
    if (flags.length === 0) flags.push('NULL');
    constraints = flags.join(' ');
    if (relation) constraints += ` REFERENCES ${relation.toTable}(${relation.toColumn})`;
  }

  const column: ParsedColumn = { name, type, constraints };
  if (defaultValue !== undefined) column.defaultValue = defaultValue;

  return { column, relation };
}

/**
 * Parse a full DDL script into ordered `ParsedTableSchema` entries.
 */
export function parseDdl(ddl: string): ParsedTableSchema[] {
  const sql = stripLineComments(ddl);
  const lines = sql.split('\n');

  // Pass 1 — collect index labels grouped by table (CREATE INDEX + ALTER TABLE UNIQUE).
  const indexesByTable = new Map<string, string[]>();
  const addIndex = (table: string, label: string) => {
    const list = indexesByTable.get(table) ?? [];
    list.push(label);
    indexesByTable.set(table, list);
  };
  for (const line of lines) {
    const idxMatch = /CREATE\s+INDEX\s+([A-Za-z_]\w*)\s+ON\s+([A-Za-z_]\w*)\s*\(([^)]*)\)/i.exec(line.trim());
    if (idxMatch) {
      addIndex(idxMatch[2], `${idxMatch[1]} (${idxMatch[3].trim()})`);
      continue;
    }
    const alterMatch = /ALTER\s+TABLE\s+([A-Za-z_]\w*)\s+ADD\s+CONSTRAINT\s+([A-Za-z_]\w*)\s+UNIQUE\s*\(([^)]*)\)/i.exec(line.trim());
    if (alterMatch) {
      addIndex(alterMatch[1], `${alterMatch[2]} (${alterMatch[3].trim()})`);
    }
  }

  // Pass 2 — CREATE TABLE blocks.
  const tables: ParsedTableSchema[] = [];
  let i = 0;
  while (i < lines.length) {
    const header = /^\s*CREATE\s+TABLE\s+([A-Za-z_]\w*)\s*\(/i.exec(lines[i]);
    if (!header) {
      i += 1;
      continue;
    }

    const name = header[1];
    const columns: ParsedColumn[] = [];
    const relations: ParsedRelation[] = [];

    let j = i + 1;
    for (; j < lines.length; j++) {
      const trimmed = lines[j].trim().replace(/;+$/, '').trim();
      if (trimmed === ')') break; // closing line of the CREATE TABLE body
      const parsed = parseColumnLine(lines[j]);
      if (parsed) {
        columns.push(parsed.column);
        if (parsed.relation) relations.push(parsed.relation);
      }
    }

    tables.push({
      name,
      columns,
      indexes: indexesByTable.get(name) ?? [],
      relations,
    });
    i = j + 1;
  }

  return tables;
}

