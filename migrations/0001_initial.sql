PRAGMA foreign_keys = ON;

CREATE TABLE accepted_batches (
  batch_id       TEXT PRIMARY KEY,
  received_day   TEXT NOT NULL CHECK (received_day GLOB '????-??-??'),
  schema_version INTEGER NOT NULL CHECK (schema_version = 1)
) WITHOUT ROWID;

CREATE INDEX accepted_batches_received_day_idx
  ON accepted_batches (received_day);

CREATE TABLE usage_aggregates (
  period_start   TEXT NOT NULL CHECK (period_start GLOB '????-??-??'),
  period_end     TEXT NOT NULL CHECK (period_end GLOB '????-??-??'),
  schema_version INTEGER NOT NULL CHECK (schema_version = 1),
  netlab_version TEXT NOT NULL CHECK (length(netlab_version) BETWEEN 3 AND 9),
  dimension      TEXT NOT NULL CHECK (
    dimension IN ('topology','node','link','provider','device','module','plugin','command')
  ),
  item           TEXT NOT NULL CHECK (length(item) BETWEEN 1 AND 64),
  observations   INTEGER NOT NULL CHECK (observations BETWEEN 1 AND 1000000000),
  instances      INTEGER NOT NULL CHECK (instances BETWEEN 0 AND 100000000000),
  maximum        INTEGER NOT NULL CHECK (maximum BETWEEN 0 AND 1000000),
  updated_day    TEXT NOT NULL CHECK (updated_day GLOB '????-??-??'),

  PRIMARY KEY (
    period_start, period_end, schema_version, netlab_version, dimension, item
  )
) WITHOUT ROWID;

CREATE INDEX usage_aggregates_dimension_item_idx
  ON usage_aggregates (dimension, item, period_end);
