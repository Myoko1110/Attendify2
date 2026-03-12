"""RBAC permission keys managed in code.

In production, we keep permission *keys* stable and managed by code.
The DB table `permissions` is used as a catalog for UI (list/description).
Use `sync_permissions_to_db()` to upsert these keys into DB.

This module also defines the *default* RBAC configuration (roles -> permissions).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDef:
    key: str
    description: str = ""


PERMISSIONS: list[PermissionDef] = [
    PermissionDef("dashboard:access", "ダッシュボードへのアクセス"),
    PermissionDef("dashboard:write", "ダッシュボードの操作"),

    PermissionDef("rbac:manage", "権限・ロールの操作"),

    PermissionDef("attendance:export", "出欠のエクスポート"),
    PermissionDef("attendance:write", "出欠の操作"),
    PermissionDef("attendance:read", "出欠の読み込み"),

    PermissionDef("member:write", "部員の操作"),
    PermissionDef("member:read", "部員の読み込み"),
    PermissionDef("member:self", "自分の読み込み"),

    PermissionDef("schedule:write", "予定の操作"),
    PermissionDef("schedule:read", "予定の読み込み"),

    PermissionDef("group:write", "グループの操作"),
    PermissionDef("group:read", "グループの読み込み"),

    PermissionDef("pre-check:write", "事前出欠の送信"),
    PermissionDef("pre-check:read", "事前出欠の読み込み"),
]


# 親権限が子権限を包括する（親を持てば子も許可）
# 例: dashboard:write => dashboard:read => dashboard:access
PERMISSION_IMPLIES: list[tuple[str, str]] = [
    ("dashboard:access", "attendance:read"),
    ("dashboard:access", "member:read"),
    ("dashboard:access", "schedule:read"),
    ("dashboard:access", "group:read"),
    ("dashboard:access", "pre-check:read"),

    ("dashboard:write", "dashboard:read"),
    ("dashboard:write", "attendance:write"),
    ("dashboard:write", "member:write"),
    ("dashboard:write", "schedule:write"),
    ("dashboard:write", "group:write"),
    ("dashboard:write", "pre-check:write"),

    ("attendance:write", "attendance:read"),
    ("member:write", "member:read"),
    ("member:read", "member:self"),
    ("schedule:write", "schedule:read"),
    ("group:write", "group:read"),

    ("dashboard:write", "dashboard:access"),

    ("pre-check:write", "pre-check:read"),
    ("pre-check:write", "schedule:read"),
    ("pre-check:write", "member:self"),
]


@dataclass(frozen=True)
class RoleDef:
    key: str
    display_name: str
    description: str = ""
    permission_keys: tuple[str, ...] = ()


# デフォルトで用意するロールと権限割当（必要に応じて増やす）
DEFAULT_ROLES: list[RoleDef] = [
    RoleDef(
        key="admin",
        display_name="管理者",
        description="すべてのアクセスを許可",
        permission_keys=(
            "dashboard:write",
            "rbac:manage",
            "attendance:export",
        ),
    ),
    RoleDef(
        key="viewer",
        display_name="閲覧者",
        description="閲覧のみを許可",
        permission_keys=(
            "dashboard:access",
            "pre-check:write",
        ),
    ),
    RoleDef(
        key="input",
        display_name="入力",
        description="出欠の入力",
        permission_keys=(
            "dashboard:access",
            "attendance:write",
            "pre-check:write",
        )
    ),
    RoleDef(
        key="default",
        display_name="デフォルト",
        description="デフォルトのロール",
        permission_keys=(
            "pre-check:write",
        )
    )
]


def permission_keys() -> list[str]:
    return [p.key for p in PERMISSIONS]
