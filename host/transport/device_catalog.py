"""Inert local knowledge catalog. Atomic versions, never tasks or device permissions."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3

from device_safe_import import ImportErrorCode, SourcePolicy, read_archive, require, sha

MAX_PACKAGES = 256
MAX_STORAGE_BYTES = 32 * 1024 * 1024


def namespace_ok(value):
    require(type(value) is str and re.fullmatch(r'[a-z][a-z0-9-]{0,60}', value), 'NAMESPACE_ERROR')


def order(version):
    return tuple(map(int, version.split('.')))


def safe_local_path(path):
    for current in (path, *path.parents):
        if current.exists():
            attr = getattr(current.lstat(), 'st_file_attributes', 0)
            require(not current.is_symlink() and not attr & 0x400, 'STORAGE_PATH_ERROR')


class Catalog:
    """Caller-controlled local namespace, not an OS multi-user authentication boundary."""
    def __init__(self, root):
        root = Path(root).absolute()
        safe_local_path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.db = root / 'catalog.sqlite'
        for name in ('catalog.sqlite', 'catalog.sqlite-journal', 'catalog.sqlite-wal', 'catalog.sqlite-shm'):
            safe_local_path(root / name)
        existed = self.db.exists()
        try:
            with closing(self._connect()) as conn:
                if not existed:
                    conn.executescript('''BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), schema_version INTEGER NOT NULL, revision INTEGER NOT NULL);
INSERT OR IGNORE INTO meta VALUES(1,1,0);
CREATE TABLE IF NOT EXISTS packages (namespace TEXT NOT NULL, package_id TEXT NOT NULL, version TEXT NOT NULL,
 digest TEXT NOT NULL, raw BLOB NOT NULL, source_status TEXT NOT NULL, imported_at TEXT NOT NULL,
 PRIMARY KEY(namespace,package_id,version));
CREATE TABLE IF NOT EXISTS history (revision INTEGER PRIMARY KEY, namespace TEXT NOT NULL,
 package_id TEXT NOT NULL, version TEXT NOT NULL, digest TEXT NOT NULL, event TEXT NOT NULL, time_utc TEXT NOT NULL);
COMMIT;''')
                require(conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'STORAGE_CORRUPT')
                row = conn.execute('SELECT schema_version, revision FROM meta WHERE id=1').fetchone()
                require(row is not None and row[0] == 1 and type(row[1]) is int and row[1] >= 0, 'STORAGE_SCHEMA_ERROR')
                conn.execute('SELECT namespace,package_id,version,digest,raw,source_status,imported_at FROM packages LIMIT 0')
                conn.execute('SELECT revision,namespace,package_id,version,digest,event,time_utc FROM history LIMIT 0')
        except sqlite3.DatabaseError:
            raise ImportErrorCode('STORAGE_CORRUPT') from None

    def _connect(self):
        safe_local_path(self.db)
        conn = sqlite3.connect(self.db, timeout=3, isolation_level=None)
        try:
            conn.execute('PRAGMA synchronous=FULL')
        except sqlite3.Error:
            conn.close()
            raise
        return conn

    def _checkpoint(self, phase):
        """Trusted subclass test seam only, never selected by archive data."""

    def revision(self):
        with closing(self._connect()) as conn:
            return conn.execute('SELECT revision FROM meta WHERE id=1').fetchone()[0]

    def import_bytes(self, namespace, raw, policy, expected_revision=None):
        namespace_ok(namespace)
        require(type(policy) is SourcePolicy, 'SOURCE_POLICY_ERROR')
        require(expected_revision is None or type(expected_revision) is int and expected_revision >= 0, 'REVISION_ERROR')
        package = read_archive(raw)
        manifest = package.manifest()
        identity = (namespace, manifest['package_id'], manifest['version'])
        source_status = policy.classify(package)
        try:
            with closing(self._connect()) as conn:
                conn.execute('BEGIN IMMEDIATE')
                revision = conn.execute('SELECT revision FROM meta WHERE id=1').fetchone()[0]
                require(expected_revision is None or expected_revision == revision, 'REVISION_CONFLICT')
                previous = conn.execute('SELECT digest,source_status,raw FROM packages WHERE namespace=? AND package_id=? AND version=?', identity).fetchone()
                if previous:
                    require(type(previous[2]) is bytes and sha(previous[2]) == previous[0], 'STORAGE_DIGEST_ERROR')
                    require(previous[0] == package.sha256, 'VERSION_CONFLICT')
                    status = 'ALREADY_IMPORTED' if previous[1] == 'TRUSTED_LOCAL_SOURCE' else 'QUARANTINED'
                    conn.rollback()
                    return self._receipt(package, status, previous[1], revision)
                count, total = conn.execute('SELECT count(*),coalesce(sum(length(raw)),0) FROM packages').fetchone()
                require(count < MAX_PACKAGES and total + len(raw) <= MAX_STORAGE_BYTES, 'STORAGE_CAPACITY')
                versions = [r[0] for r in conn.execute('SELECT version FROM packages WHERE namespace=? AND package_id=? AND source_status=?',
                                                       (namespace, manifest['package_id'], 'TRUSTED_LOCAL_SOURCE'))]
                if source_status != 'TRUSTED_LOCAL_SOURCE':
                    status = 'QUARANTINED'
                elif not versions:
                    status = 'IMPORTED'
                elif order(manifest['version']) > max(map(order, versions)):
                    status = 'IMPORTED_UPGRADE'
                else:
                    status = 'IMPORTED_INACTIVE_OLDER'
                now = datetime.now(timezone.utc).isoformat()
                conn.execute('INSERT INTO packages VALUES(?,?,?,?,?,?,?)', (*identity, package.sha256, raw, source_status, now))
                self._checkpoint('AFTER_INSERT')
                revision += 1
                conn.execute('INSERT INTO history VALUES(?,?,?,?,?,?,?)', (revision, *identity, package.sha256, status, now))
                conn.execute('UPDATE meta SET revision=? WHERE id=1', (revision,))
                self._checkpoint('BEFORE_COMMIT')
                conn.commit()
                return self._receipt(package, status, source_status, revision)
        except ImportErrorCode:
            raise
        except (sqlite3.Error, OSError):
            raise ImportErrorCode('STORAGE_WRITE_ERROR') from None

    @staticmethod
    def _receipt(package, status, source_status, revision):
        return {**package.receipt(), 'status': status, 'source_trust': source_status,
                'revision': revision, 'local_execution_approval': 'NOT_GRANTED',
                'formal_gate': 'LOCAL_REVIEW_AND_FRESH_RUNTIME_REQUIRED'}

    def list_packages(self, namespace, limit=20):
        namespace_ok(namespace)
        require(type(limit) is int and 1 <= limit <= 100, 'LIMIT_ERROR')
        with closing(self._connect()) as conn:
            rows = conn.execute('SELECT package_id,version,digest,source_status FROM packages WHERE namespace=? ORDER BY package_id,version', (namespace,)).fetchall()
        latest = {}
        for id_, ver, _, source in rows:
            if source == 'TRUSTED_LOCAL_SOURCE' and (id_ not in latest or order(ver) > order(latest[id_])): latest[id_] = ver
        return [{'package_id': id_, 'version': ver, 'sha256': digest, 'source_trust': source,
                 'latest_knowledge_version': latest.get(id_), 'execution_authority': False,
                 'formal_retrievable': False} for id_, ver, digest, source in rows[:limit]]

    def load(self, namespace, package_id, version):
        namespace_ok(namespace)
        require(type(package_id) is str and type(version) is str, 'PACKAGE_REFERENCE_ERROR')
        with closing(self._connect()) as conn:
            row = conn.execute('SELECT raw,digest,source_status FROM packages WHERE namespace=? AND package_id=? AND version=?',
                               (namespace, package_id, version)).fetchone()
        require(row is not None, 'PACKAGE_NOT_FOUND')
        require(row[2] == 'TRUSTED_LOCAL_SOURCE', 'QUARANTINED')
        require(type(row[0]) is bytes and sha(row[0]) == row[1], 'STORAGE_DIGEST_ERROR')
        package = read_archive(row[0])
        require(package.manifest()['package_id'] == package_id and package.manifest()['version'] == version, 'STORAGE_IDENTITY_ERROR')
        return package

    def history(self, namespace):
        namespace_ok(namespace)
        with closing(self._connect()) as conn:
            rows = conn.execute('SELECT revision,package_id,version,digest,event,time_utc FROM history WHERE namespace=? ORDER BY revision', (namespace,)).fetchall()
        return [dict(zip(('revision', 'package_id', 'version', 'sha256', 'event', 'time_utc'), row)) for row in rows]
