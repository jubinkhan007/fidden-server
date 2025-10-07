# api/migrations/0043_drop_default_columns.py
from django.db import migrations

SQL = """
ALTER TABLE api_shop
  DROP COLUMN IF EXISTS default_is_deposit_required,
  DROP COLUMN IF EXISTS default_deposit_amount,
  DROP COLUMN IF EXISTS default_free_cancellation_hours,
  DROP COLUMN IF EXISTS default_cancellation_fee_percentage,
  DROP COLUMN IF EXISTS default_no_refund_hours;
"""

class Migration(migrations.Migration):

    dependencies = [
        ("api", "0042_remove_shop_stripe_customer_id"),
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql=migrations.RunSQL.noop),
    ]
