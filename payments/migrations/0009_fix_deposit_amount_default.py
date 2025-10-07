from django.db import migrations

SQL_FORWARD = """
ALTER TABLE payments_payment
    ALTER COLUMN deposit_amount SET DEFAULT 0;

UPDATE payments_payment
   SET deposit_amount = 0
 WHERE deposit_amount IS NULL;

ALTER TABLE payments_payment
    ALTER COLUMN deposit_amount SET NOT NULL;
"""

SQL_REVERSE = """
-- Keep as-is (no-op), or relax if you want:
-- ALTER TABLE payments_payment ALTER COLUMN deposit_amount DROP NOT NULL;
-- ALTER TABLE payments_payment ALTER COLUMN deposit_amount DROP DEFAULT;
"""

class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0007_payment_balance_paid'),
    ]

    operations = [
        migrations.RunSQL(SQL_FORWARD, reverse_sql=SQL_REVERSE),
    ]
