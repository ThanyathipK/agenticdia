// ============================================================================
// Shared schema type contracts.
//
// `ParsedTableSchema` / `ParsedColumn` are the raw output of the DDL parser
// (structure only, derived from backend/init.sql). `TableSchema` / `ColumnDefinition`
// are the enriched shape consumed by the Schema Explorer UI (structure + the
// human-authored descriptions & banking context that are *not* part of the DDL).
// ============================================================================

/** A single column as parsed from the DDL (no presentation text yet). */
export interface ParsedColumn {
  name: string;
  type: string;
  constraints: string;
  defaultValue?: string;
}

/** A foreign key edge between two tables. */
export interface ParsedRelation {
  fromColumn: string;
  toTable: string;
  toColumn: string;
  onDelete: 'CASCADE' | 'RESTRICT' | 'SET NULL' | 'NONE';
}

/** A table's structure as parsed from the DDL (no presentation text yet). */
export interface ParsedTableSchema {
  name: string;
  columns: ParsedColumn[];
  indexes: string[];
  relations: ParsedRelation[];
}

/** Enriched column shape consumed by the Schema Explorer datagrid / panels. */
export interface ColumnDefinition {
  name: string;
  type: string;
  constraints: string;
  defaultValue?: string;
  description: string;
}

/** Enriched table shape consumed by the Schema Explorer datagrid / panels. */
export interface TableSchema {
  name: string;
  description: string;
  bankingContext: string;
  columns: ColumnDefinition[];
  indexes: string[];
  relations: {
    fromColumn: string;
    toTable: string;
    toColumn: string;
    onDelete: 'CASCADE' | 'RESTRICT' | 'SET NULL' | 'NONE';
  }[];
}
