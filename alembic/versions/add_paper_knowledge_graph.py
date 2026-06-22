"""add paper knowledge graph tables

Revision ID: add_paper_knowledge_graph
Revises: add_workspaces
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_paper_knowledge_graph'
down_revision: Union[str, Sequence[str], None] = 'add_workspaces'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paper_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False, server_default=""),
        sa.Column("year", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("authors", sa.String(1000), nullable=False, server_default=""),
        sa.Column("abstract", sa.Text(), nullable=False, server_default=""),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filename"),
    )
    op.create_index("ix_paper_nodes_id", "paper_nodes", ["id"])
    op.create_index("ix_paper_nodes_filename", "paper_nodes", ["filename"])

    op.create_table(
        "citation_edges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_id"], ["paper_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["paper_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_citation_edges_id", "citation_edges", ["id"])
    op.create_index("ix_citation_edges_source_id", "citation_edges", ["source_id"])
    op.create_index("ix_citation_edges_target_id", "citation_edges", ["target_id"])

    op.create_table(
        "glossary_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(200), nullable=False),
        sa.Column("definition", sa.String(1000), nullable=False),
        sa.Column("chunk_id", sa.String(512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["paper_id"], ["paper_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_glossary_entries_id", "glossary_entries", ["id"])
    op.create_index("ix_glossary_entries_paper_id", "glossary_entries", ["paper_id"])


def downgrade() -> None:
    op.drop_table("glossary_entries")
    op.drop_table("citation_edges")
    op.drop_table("paper_nodes")
