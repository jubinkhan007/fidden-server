from django.db import migrations, models

SQL_FORWARD = """
ALTER TABLE payments_payment
    ALTER COLUMN balance_paid DROP DEFAULT;

ALTER TABLE payments_payment
    ALTER COLUMN balance_paid
    TYPE numeric(10,2)
    USING CASE
        WHEN balance_paid IS TRUE THEN 1
        WHEN balance_paid IS FALSE THEN 0
        ELSE 0
    END;

UPDATE payments_payment SET balance_paid = 0 WHERE balance_paid IS NULL;

ALTER TABLE payments_payment
    ALTER COLUMN balance_paid SET DEFAULT 0,
    ALTER COLUMN balance_paid SET NOT NULL;
"""

SQL_REVERSE = """
ALTER TABLE payments_payment
    ALTER COLUMN balance_paid DROP DEFAULT;

ALTER TABLE payments_payment
    ALTER COLUMN balance_paid
    TYPE boolean
    USING CASE WHEN balance_paid::numeric <> 0 THEN TRUE ELSE FALSE END;

ALTER TABLE payments_payment
    ALTER COLUMN balance_paid SET DEFAULT FALSE,
    ALTER COLUMN balance_paid SET NOT NULL;
"""

class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0007_payment_balance_paid'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(SQL_FORWARD, reverse_sql=SQL_REVERSE),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name='payment',
                    name='balance_paid',
                    field=models.DecimalField(max_digits=10, decimal_places=2, default=0),
                ),
            ],
        ),
    ]
