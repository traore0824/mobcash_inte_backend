"""
Backup / restore des champs chiffrés (valeurs brutes DB, sans re-chiffrement).

Champs concernés :
  - accounts_appname.hash / cashierpass
  - mobcash_inte_setting.connect_pro_token / connect_pro_refresh
    (+ expired_connect_pro_token pour cohérence Connect)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection
from django.utils.dateparse import parse_datetime

DEFAULT_BACKUP_NAME = ".encrypted_fields_backup.json"


def default_backup_path() -> Path:
    return Path(settings.BASE_DIR) / DEFAULT_BACKUP_NAME


def _table_columns(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            """,
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


def backup_encrypted_fields() -> dict[str, Any]:
    """Lit les valeurs brutes en SQL (indépendant du nom ORM _hash vs hash)."""
    payload: dict[str, Any] = {
        "version": 1,
        "app_names": [],
        "settings": [],
    }

    app_table = "accounts_appname"
    app_cols = _table_columns(app_table)
    if "id" in app_cols and ("hash" in app_cols or "cashierpass" in app_cols):
        select_cols = ["id"]
        if "hash" in app_cols:
            select_cols.append("hash")
        if "cashierpass" in app_cols:
            select_cols.append("cashierpass")
        if "name" in app_cols:
            select_cols.append("name")
        sql = f"SELECT {', '.join(select_cols)} FROM {app_table}"
        with connection.cursor() as cursor:
            cursor.execute(sql)
            colnames = [c[0] for c in cursor.description]
            for row in cursor.fetchall():
                data = dict(zip(colnames, row))
                payload["app_names"].append(
                    {
                        "id": str(data["id"]),
                        "name": data.get("name"),
                        "hash": data.get("hash"),
                        "cashierpass": data.get("cashierpass"),
                    }
                )

    setting_table = "mobcash_inte_setting"
    setting_cols = _table_columns(setting_table)
    token_col = (
        "connect_pro_token"
        if "connect_pro_token" in setting_cols
        else None
    )
    refresh_col = (
        "connect_pro_refresh"
        if "connect_pro_refresh" in setting_cols
        else None
    )
    if "id" in setting_cols and (token_col or refresh_col):
        select_cols = ["id"]
        if token_col:
            select_cols.append(token_col)
        if refresh_col:
            select_cols.append(refresh_col)
        if "expired_connect_pro_token" in setting_cols:
            select_cols.append("expired_connect_pro_token")
        sql = f"SELECT {', '.join(select_cols)} FROM {setting_table}"
        with connection.cursor() as cursor:
            cursor.execute(sql)
            colnames = [c[0] for c in cursor.description]
            for row in cursor.fetchall():
                data = dict(zip(colnames, row))
                expired = data.get("expired_connect_pro_token")
                payload["settings"].append(
                    {
                        "id": str(data["id"]),
                        "connect_pro_token": data.get("connect_pro_token"),
                        "connect_pro_refresh": data.get("connect_pro_refresh"),
                        "expired_connect_pro_token": (
                            expired.isoformat() if expired else None
                        ),
                    }
                )

    return payload


def write_backup(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_backup(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return {"version": 0, "app_names": raw, "settings": []}
    return raw


def restore_encrypted_fields(payload: dict[str, Any], *, dry_run: bool = False) -> dict[str, int]:
    """
    Réécrit les valeurs brutes via SQL UPDATE (pas de property → pas de double encrypt).
    """
    stats = {
        "apps_restored": 0,
        "apps_skipped": 0,
        "settings_restored": 0,
        "settings_skipped": 0,
    }

    app_table = "accounts_appname"
    app_cols = _table_columns(app_table)
    for row in payload.get("app_names") or []:
        app_id = row.get("id")
        if not app_id:
            stats["apps_skipped"] += 1
            continue
        sets = []
        params: list[Any] = []
        if "hash" in app_cols and "hash" in row:
            sets.append("hash = %s")
            params.append(row.get("hash"))
        if "cashierpass" in app_cols and "cashierpass" in row:
            sets.append("cashierpass = %s")
            params.append(row.get("cashierpass"))
        if not sets:
            stats["apps_skipped"] += 1
            continue
        params.append(app_id)
        sql = f"UPDATE {app_table} SET {', '.join(sets)} WHERE id = %s"
        if dry_run:
            stats["apps_restored"] += 1
            continue
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            if cursor.rowcount:
                stats["apps_restored"] += 1
            else:
                stats["apps_skipped"] += 1

    setting_table = "mobcash_inte_setting"
    setting_cols = _table_columns(setting_table)
    for row in payload.get("settings") or []:
        setting_id = row.get("id")
        if not setting_id:
            stats["settings_skipped"] += 1
            continue
        sets = []
        params = []
        if "connect_pro_token" in setting_cols and "connect_pro_token" in row:
            sets.append("connect_pro_token = %s")
            params.append(row.get("connect_pro_token"))
        if "connect_pro_refresh" in setting_cols and "connect_pro_refresh" in row:
            sets.append("connect_pro_refresh = %s")
            params.append(row.get("connect_pro_refresh"))
        if (
            "expired_connect_pro_token" in setting_cols
            and "expired_connect_pro_token" in row
        ):
            expired_raw = row.get("expired_connect_pro_token")
            sets.append("expired_connect_pro_token = %s")
            params.append(parse_datetime(expired_raw) if expired_raw else None)
        if not sets:
            stats["settings_skipped"] += 1
            continue
        params.append(setting_id)
        sql = f"UPDATE {setting_table} SET {', '.join(sets)} WHERE id = %s"
        if dry_run:
            stats["settings_restored"] += 1
            continue
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            if cursor.rowcount:
                stats["settings_restored"] += 1
            else:
                stats["settings_skipped"] += 1

    return stats
