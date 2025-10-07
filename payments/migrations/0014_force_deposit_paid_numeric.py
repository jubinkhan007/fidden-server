from django.db import migrations

SQL_FORWARD = """
DO $$
BEGIN
  -- Detect current type precisely in public schema
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='payments_payment'
      AND column_name='deposit_paid'
      AND data_type='boolean'
  ) THEN
    -- Drop any default (it's NULL currently), change type using safe boolean mapping,
    -- then enforce default 0 and NOT NULL.
    ALTER TABLE public.payments_payment
      ALTER COLUMN deposit_paid DROP DEFAULT;

    ALTER TABLE public.payments_payment
      ALTER COLUMN deposit_paid TYPE numeric(10,2)
      USING CASE WHEN deposit_paid THEN 1 ELSE 0 END;

    ALTER TABLE public.payments_payment
      ALTER COLUMN deposit_paid SET DEFAULT 0,
      ALTER COLUMN deposit_paid SET NOT NULL;

  ELSIF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='payments_payment'
      AND column_name='deposit_paid'
      AND data_type='numeric'
  ) THEN
    -- If it's already numeric, just normalize NULLs/defaults for safety.
    UPDATE public.payments_payment
       SET deposit_paid = 0
     WHERE deposit_paid IS NULL;

    ALTER TABLE public.payments_payment
      ALTER COLUMN deposit_paid SET DEFAULT 0,
      ALTER COLUMN deposit_paid SET NOT NULL;
  END IF;
END
$$;
"""

class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0013_fix_deposit_paid_type'),  # use your latest migration filename here
    ]

    operations = [
        migrations.RunSQL(SQL_FORWARD, migrations.RunSQL.noop),
    ]
