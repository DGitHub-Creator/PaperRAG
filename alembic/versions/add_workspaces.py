"""add workspaces

Revision ID: add_workspaces
Revises: 21f6caf0b15b
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_workspaces'
down_revision: Union[str, Sequence[str], None] = '21f6caf0b15b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建 workspaces 表
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_id", "workspaces", ["id"])
    op.create_index("ix_workspaces_owner_id", "workspaces", ["owner_id"])

    # 创建 workspace_members 表
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_members_id", "workspace_members", ["id"])
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])

    # 为 chat_sessions 添加 workspace_id 外键
    op.add_column(
        "chat_sessions",
        sa.Column("workspace_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_chat_sessions_workspace_id", "chat_sessions", ["workspace_id"])
    op.create_foreign_key(
        "fk_chat_sessions_workspace_id",
        "chat_sessions",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # 移除 chat_sessions 的 workspace_id 列
    op.drop_constraint("fk_chat_sessions_workspace_id", "chat_sessions", type_="foreignkey")
    op.drop_index("ix_chat_sessions_workspace_id", "chat_sessions")
    op.drop_column("chat_sessions", "workspace_id")

    # 删除 workspace_members 表
    op.drop_table("workspace_members")

    # 删除 workspaces 表
    op.drop_table("workspaces")
