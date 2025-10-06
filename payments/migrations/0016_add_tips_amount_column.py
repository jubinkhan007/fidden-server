from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0014_force_deposit_paid_numeric"),  # update if your latest differs
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE payments_payment
                ADD COLUMN IF NOT EXISTS tips_amount numeric(10,2) DEFAULT 0 NOT NULL;
            """,
            reverse_sql="""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='payments_payment' AND column_name='tips_amount'
                    ) THEN
                        ALTER TABLE payments_payment DROP COLUMN tips_amount;
                    END IF;
                END$$;
            """,
        ),
    ]
