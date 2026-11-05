from alembic import op
import sqlalchemy as sa

revision = "0d1e2f3a4b5c"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user", sa.Column("role", sa.String(length=7), nullable=False, server_default="member")
    )
    op.execute(sa.text("UPDATE \"user\" SET role = 'admin' WHERE is_superuser = true"))
    op.create_check_constraint("user_role", "user", "role IN ('admin', 'manager', 'member')")
    op.drop_column("user", "is_superuser")


def downgrade():
    op.add_column(
        "user", sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.execute(sa.text("UPDATE \"user\" SET is_superuser = true WHERE role = 'admin'"))
    op.alter_column("user", "is_superuser", server_default=None)
    op.drop_constraint("user_role", "user", type_="check")
    op.drop_column("user", "role")
