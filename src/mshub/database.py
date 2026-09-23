from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    name TEXT NOT NULL,
    item_type TEXT NOT NULL DEFAULT 'skill',
    author TEXT NOT NULL,
    repo TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'github',
    library TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    ref TEXT NOT NULL DEFAULT 'HEAD',
    subdir TEXT NOT NULL DEFAULT '',
    local_dir TEXT NOT NULL,
    version TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    commit_date TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    description_zh TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    has_scripts INTEGER NOT NULL DEFAULT 0,
    security_status TEXT NOT NULL DEFAULT 'unchecked',
    security_route TEXT NOT NULL DEFAULT '',
    security_findings TEXT NOT NULL DEFAULT '[]',
    install_mode TEXT NOT NULL DEFAULT 'standard',
    fetcher TEXT NOT NULL DEFAULT 'archive',
    license_name TEXT NOT NULL DEFAULT '',
    imported_from TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT '',
    installed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (name, library)
);
CREATE INDEX IF NOT EXISTS idx_skills_author ON skills(author);
CREATE INDEX IF NOT EXISTS idx_skills_security ON skills(security_status);
CREATE INDEX IF NOT EXISTS idx_skills_dir ON skills(local_dir);
"""

# 身份与归属分离（v0.6.0）：name = 作者/仓库[/子目录]（本地自研为 local/目录名），
# 是纯身份；唯一性由 (name, library) 复合键保证——同一技能在多个库的分身
# 同名不同库，互不覆盖。旧版把库名揉进 name（库名/目录名）作主键，
# 由 _migrate_composite_key + recovery.canonicalize_library_names 迁移。
COLUMNS = [
    "name", "item_type", "author", "repo", "provider", "library", "source_url", "ref", "subdir",
    "local_dir", "version", "commit_hash", "commit_date", "description", "description_zh",
    "tags", "has_scripts", "security_status", "security_route", "security_findings",
    "install_mode", "fetcher", "license_name", "imported_from", "imported_at", "installed_at", "updated_at",
]


class Database:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.meta_dir = repo_root / ".meta"
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.meta_dir / "skills.db"
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(skills)").fetchall()
            }
            if "tags" not in columns:
                connection.execute(
                    "ALTER TABLE skills ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'"
                )
            if "item_type" not in columns:
                connection.execute(
                    "ALTER TABLE skills ADD COLUMN item_type TEXT NOT NULL DEFAULT 'skill'"
                )
            if "library" not in columns:
                connection.execute(
                    "ALTER TABLE skills ADD COLUMN library TEXT NOT NULL DEFAULT ''"
                )
            if "description_zh" not in columns:
                connection.execute(
                    "ALTER TABLE skills ADD COLUMN description_zh TEXT NOT NULL DEFAULT ''"
                )
            if "imported_from" not in columns:
                connection.execute("ALTER TABLE skills ADD COLUMN imported_from TEXT NOT NULL DEFAULT ''")
            if "imported_at" not in columns:
                connection.execute("ALTER TABLE skills ADD COLUMN imported_at TEXT NOT NULL DEFAULT ''")
            self._migrate_composite_key(connection)
            # 表重建会连带丢索引，统一在末尾补建
            connection.execute("CREATE INDEX IF NOT EXISTS idx_skills_author ON skills(author)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_skills_security ON skills(security_status)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_skills_dir ON skills(local_dir)")

    def _migrate_composite_key(self, connection: sqlite3.Connection) -> None:
        """旧库主键是 name 单列：重建为 (name, library) 复合主键，数据原样搬移。"""
        info = connection.execute("PRAGMA table_info(skills)").fetchall()
        pk_columns = [
            row["name"]
            for row in sorted((row for row in info if row["pk"]), key=lambda row: row["pk"])
        ]
        if pk_columns != ["name"]:
            return
        existing_columns = [row["name"] for row in info]
        missing = [column for column in COLUMNS if column not in existing_columns]
        if missing:
            return  # 列补齐迁移异常时不动表结构，避免丢列
        column_list = ", ".join(COLUMNS)
        connection.executescript(f"""
            CREATE TABLE skills_rekeyed (
                name TEXT NOT NULL,
                item_type TEXT NOT NULL DEFAULT 'skill',
                author TEXT NOT NULL,
                repo TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'github',
                library TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL,
                ref TEXT NOT NULL DEFAULT 'HEAD',
                subdir TEXT NOT NULL DEFAULT '',
                local_dir TEXT NOT NULL,
                version TEXT NOT NULL,
                commit_hash TEXT NOT NULL,
                commit_date TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                description_zh TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                has_scripts INTEGER NOT NULL DEFAULT 0,
                security_status TEXT NOT NULL DEFAULT 'unchecked',
                security_route TEXT NOT NULL DEFAULT '',
                security_findings TEXT NOT NULL DEFAULT '[]',
                install_mode TEXT NOT NULL DEFAULT 'standard',
                fetcher TEXT NOT NULL DEFAULT 'archive',
                license_name TEXT NOT NULL DEFAULT '',
                imported_from TEXT NOT NULL DEFAULT '',
                imported_at TEXT NOT NULL DEFAULT '',
                installed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (name, library)
            );
            INSERT INTO skills_rekeyed ({column_list})
            SELECT {column_list} FROM skills;
            DROP TABLE skills;
            ALTER TABLE skills_rekeyed RENAME TO skills;
        """)

    def list_skills(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM skills ORDER BY lower(name), library"
            ).fetchall()
        return [self._decode(row) for row in rows]

    def get_skill(self, name: str, library: str | None = None) -> dict[str, Any] | None:
        with self.connect() as connection:
            if library:
                row = connection.execute(
                    "SELECT * FROM skills WHERE name = ? AND library = ?", (name, library)
                ).fetchone()
                return self._decode(row) if row else None
            rows = connection.execute(
                "SELECT * FROM skills WHERE name = ? ORDER BY library", (name,)
            ).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            libraries = "、".join(row["library"] or "(flat)" for row in rows)
            from .errors import ConflictError

            raise ConflictError(f"「{name}」在多个库中各有一份（{libraries}），操作时需要指定库。")
        return self._decode(rows[0])

    def get_skill_by_dir(self, local_dir: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM skills WHERE local_dir = ?", (local_dir,)
            ).fetchone()
        return self._decode(row) if row else None

    def upsert_skill(self, record: dict[str, Any]) -> None:
        values = []
        for column in COLUMNS:
            value = record.get(column, "")
            if column == "item_type" and not value:
                value = "skill"
            if column in {"security_findings", "tags"}:
                value = json.dumps(value or [], ensure_ascii=False)
            if column == "has_scripts":
                value = int(bool(value))
            values.append(value)
        placeholders = ", ".join("?" for _ in COLUMNS)
        updates = ", ".join(
            f"{column}=excluded.{column}" for column in COLUMNS if column not in {"name", "library"}
        )
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO skills ({', '.join(COLUMNS)}) VALUES ({placeholders}) "
                f"ON CONFLICT(name, library) DO UPDATE SET {updates}",
                values,
            )

    def update_fields(
        self, name: str, updates: dict[str, Any], library: str | None = None
    ) -> None:
        if not updates:
            return
        allowed = {
            "name", "version", "commit_hash", "commit_date", "description", "description_zh",
            "has_scripts", "security_status", "security_route", "security_findings",
            "install_mode", "fetcher", "license_name", "updated_at", "ref", "subdir", "tags",
            "item_type", "library", "author", "repo", "provider", "source_url", "local_dir",
            "imported_from", "imported_at",
        }
        clean = {key: value for key, value in updates.items() if key in allowed}
        if not clean:
            return
        for field in ("security_findings", "tags"):
            if field in clean:
                clean[field] = json.dumps(clean[field] or [], ensure_ascii=False)
        if "has_scripts" in clean:
            clean["has_scripts"] = int(bool(clean["has_scripts"]))
        assignments = ", ".join(f"{column} = ?" for column in clean)
        conditions = "name = ?"
        params = [*clean.values(), name]
        if library:
            conditions += " AND library = ?"
            params.append(library)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE skills SET {assignments} WHERE {conditions}",
                params,
            )

    def delete_skill(self, name: str, library: str | None = None) -> None:
        with self.connect() as connection:
            if library:
                connection.execute(
                    "DELETE FROM skills WHERE name = ? AND library = ?", (name, library)
                )
            else:
                connection.execute("DELETE FROM skills WHERE name = ?", (name,))

    def rename_skill(self, old_name: str, new_name: str, library: str | None = None) -> None:
        self.update_fields(old_name, {"name": new_name}, library=library)

    def rename_skill_by_dir(self, local_dir: str, new_name: str, library: str = "") -> None:
        """Rename one record identified by its stable on-disk directory.

        Historical records can have an empty name, so name is not a safe key for
        repairing them.  The directory plus library pair is stable and is also
        the pair used by manifests during cross-machine recovery.
        """
        with self.connect() as connection:
            connection.execute(
                "UPDATE skills SET name = ? WHERE local_dir = ? AND library = ?",
                (new_name, local_dir, library),
            )

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["has_scripts"] = bool(data["has_scripts"])
        try:
            data["security_findings"] = json.loads(data["security_findings"] or "[]")
        except json.JSONDecodeError:
            data["security_findings"] = []
        try:
            data["tags"] = json.loads(data.get("tags") or "[]")
            if not isinstance(data["tags"], list):
                data["tags"] = []
        except json.JSONDecodeError:
            data["tags"] = []
        return data
