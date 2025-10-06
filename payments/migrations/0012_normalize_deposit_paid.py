from django.db import migrations, models

SQL_FORWARD = r"""
DO $$
BEGIN
  -- 1) Create deposit_paid if it doesn't exist
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='payments_payment' AND column_name='deposit_paid'
  ) THEN
    EXECUTE 'ALTER TABLE payments_payment ADD COLUMN deposit_paid numeric(10,2) DEFAULT 0 NOT NULL';
    RETURN;
  END IF;

  -- 2) If it's already numeric, just normalize defaults / not null and exit
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='payments_payment' AND column_name='deposit_paid' AND data_type='numeric'
  ) THEN
    EXECUTE 'UPDATE payments_payment SET deposit_paid = 0 WHERE deposit_paid IS NULL';
    EXECUTE 'ALTER TABLE payments_payment ALTER COLUMN deposit_paid SET DEFAULT 0';
    EXECUTE 'ALTER TABLE payments_payment ALTER COLUMN deposit_paid SET NOT NULL';
    RETURN;
  END IF;

  -- 3) For any other type, rebuild safely via a temp column
  --    (works for boolean, text, integers, etc.)
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='payments_payment' AND column_name='deposit_paid'
  ) THEN
    -- create temp numeric column
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name='payments_payment' AND column_name='deposit_paid_num'
    ) THEN
      EXECUTE 'ALTER TABLE payments_payment ADD COLUMN deposit_paid_num numeric(10,2)';
    END IF;

    -- copy with robust coercion using pg_typeof()
    EXECUTE $cpy$
      UPDATE payments_payment
      SET deposit_paid_num = CASE
        WHEN pg_typeof(deposit_paid)::text = 'boolean'
          THEN CASE WHEN deposit_paid THEN 1 ELSE 0 END
        WHEN pg_typeof(deposit_paid)::text IN ('integer','smallint','bigint')
          THEN deposit_paid::numeric
        WHEN pg_typeof(deposit_paid)::text = 'numeric'
          THEN deposit_paid
        WHEN pg_typeof(deposit_paid)::text = 'text'
          THEN CASE
                 WHEN deposit_paid IN ('t','true','1') THEN 1
                 WHEN deposit_paid IN ('f','false','0') THEN 0
                 ELSE NULL
               END
        ELSE NULL
      END
    $cpy$;

    -- fill any NULLs with 0
    EXECUTE 'UPDATE payments_payment SET deposit_paid_num = 0 WHERE deposit_paid_num IS NULL';

    -- swap columns
    EXECUTE 'ALTER TABLE payments_payment DROP COLUMN deposit_paid';
    EXECUTE 'ALTER TABLE payments_payment RENAME COLUMN deposit_paid_num TO deposit_paid';

    -- enforce constraints
    EXECUTE 'ALTER TABLE payments_payment ALTER COLUMN deposit_paid SET DEFAULT 0';
    EXECUTE 'ALTER TABLE payments_payment ALTER COLUMN deposit_paid SET NOT NULL';
  END IF;
END$$;
"""

class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0011_payment_deposit_amount'),  # keep your current dependency
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(SQL_FORWARD, migrations.RunSQL.noop)],
            state_operations=[
                # Ensure Django model state includes the field.
                migrations.AddField(
                    model_name='payment',
                    name='deposit_paid',
                    field=models.DecimalField(max_digits=10, decimal_places=2, default=0),
                ),
            ],
        ),
    ]
