"""empty message

Revision ID: 8d2db133cae5
Revises: 98535ecf4791
Create Date: 2023-03-28 22:05:08.244819

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8d2db133cae5'
down_revision = '98535ecf4791'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('employees', sa.Column('allocated_hours', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('vehicles', sa.Column('allocated_km', sa.Float(), nullable=False, server_default='0'))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('vehicles', 'allocated_km')
    op.drop_column('employees', 'allocated_hours')
    # ### end Alembic commands ###
