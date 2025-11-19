
DROP TABLE IF EXISTS mount_volumes;
DROP TABLE IF EXISTS sync_configs;

CREATE TABLE sync_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Default Config',
    source_path TEXT NOT NULL DEFAULT '/C_Drive',
    replica_path TEXT NOT NULL DEFAULT '/app/sync_replica',
    pattern TEXT DEFAULT '*',
    interval INTEGER DEFAULT 10,
    retention_days INTEGER DEFAULT 60,
    is_active BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mount_volumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    host_path TEXT NOT NULL UNIQUE,
    container_path TEXT NOT NULL UNIQUE,
    display_order INTEGER DEFAULT 0,
    is_enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
