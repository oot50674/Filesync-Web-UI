
DROP TABLE IF EXISTS sync_configs;

CREATE TABLE sync_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Default Config',
    source_path TEXT NOT NULL DEFAULT 'C:/',
    replica_path TEXT NOT NULL DEFAULT 'D:/backup',
    pattern TEXT DEFAULT '*',
    interval INTEGER DEFAULT 10,
    retention_days INTEGER DEFAULT 60,
    retention_mode TEXT DEFAULT 'days',
    retention_files INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
