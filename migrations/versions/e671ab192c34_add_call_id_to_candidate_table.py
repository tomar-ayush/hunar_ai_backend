"""add call_id to candidate table

Revision ID: e671ab192c34
Revises: d5276d984c56
Create Date: 2026-09-06 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e671ab192c34'
down_revision: Union[str, Sequence[str], None] = 'd5276d984c56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('candidate', sa.Column('call_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('candidate', 'call_id')
