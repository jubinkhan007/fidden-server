from django.db import migrations, models

SQL_FORWARD = """
DO $$
BEGIN
  -- payment_type → default 'full', NOT NULL
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='payments_payment' AND column_name='payment_type'
  )
  THEN
    UPDATE public.payments_payment SET payment_type = 'full' WHERE payment_type IS NULL;
    ALTER TABLE public.payments_payment ALTER COLUMN payment_type SET DEFAULT 'full';
    ALTER TABLE public.payments_payment ALTER COLUMN payment_type SET NOT NULL;
  END IF;

  -- tips_amount → default 0, NOT NULL (if present)
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='payments_payment' AND column_name='tips_amount'
  )
  THEN
    UPDATE public.payments_payment SET tips_amount = 0 WHERE tips_amount IS NULL;
    ALTER TABLE public.payments_payment ALTER COLUMN tips_amount SET DEFAULT 0;
    ALTER TABLE public.payments_payment ALTER COLUMN tips_amount SET NOT NULL;
  END IF;

  -- application_fee_amount → default 0, NOT NULL (if present)
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='payments_payment' AND column_name='application_fee_amount'
  )
  THEN
    UPDATE public.payments_payment SET application_fee_amount = 0 WHERE application_fee_amount IS NULL;
    ALTER TABLE public.payments_payment ALTER COLUMN application_fee_amount SET DEFAULT 0;
    ALTER TABLE public.payments_payment ALTER COLUMN application_fee_amount SET NOT NULL;
  END IF;

  -- balance_paid → default 0, NOT NULL (already numeric per your schema)
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='payments_payment' AND column_name='balance_paid'
  )
  THEN
    UPDATE public.payments_payment SET balance_paid = 0 WHERE balance_paid IS NULL;
    ALTER TABLE public.payments_payment ALTER COLUMN balance_paid SET DEFAULT 0;
    ALTER TABLE public.payments_payment ALTER COLUMN balance_paid SET NOT NULL;
  END IF;

  -- deposit_amount → default 0, NOT NULL
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='payments_payment' AND column_name='deposit_amount'
  )
  THEN
    UPDATE public.payments_payment SET deposit_amount = 0 WHERE deposit_amount IS NULL;
    ALTER TABLE public.payments_payment ALTER COLUMN deposit_amount SET DEFAULT 0;
    ALTER TABLE public.payments_payment ALTER COLUMN deposit_amount SET NOT NULL;
  END IF;

  -- deposit_paid → ensure numeric(10,2), default 0, NOT NULL
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='payments_payment' AND column_name='deposit_paid'
  )
  THEN
    -- if it is boolean, convert to 0/1 numerically
    IF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema='public' AND table_name='payments_payment'
        AND column_name='deposit_paid' AND data_type='boolean'
    ) THEN
      ALTER TABLE public.payments_payment ALTER COLUMN deposit_paid DROP DEFAULT;
      ALTER TABLE public.payments_payment
        ALTER COLUMN deposit_paid TYPE numeric(10,2)
        USING CASE WHEN deposit_paid THEN 1 ELSE 0 END;
    END IF;

    UPDATE public.payments_payment SET deposit_paid = 0 WHERE deposit_paid IS NULL;
    ALTER TABLE public.payments_payment ALTER COLUMN deposit_paid SET DEFAULT 0;
    ALTER TABLE public.payments_payment ALTER COLUMN deposit_paid SET NOT NULL;
  END IF;
END
$$;
"""

class Migration(migrations.Migration):

    # set this to the latest applied migration in your project
    dependencies = [
        ('payments', '0014_force_deposit_paid_numeric'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(SQL_FORWARD, migrations.RunSQL.noop),
            ],
            state_operations=[
                # Bring legacy columns into Django's state WITHOUT touching DB structure.
                # Only add if you actually want the ORM to know about them.
                migrations.AddField(
                    model_name='payment',
                    name='payment_type',
                    field=models.CharField(max_length=20, default='full'),
                ),
                migrations.AddField(
                    model_name='payment',
                    name='tips_amount',
                    field=models.DecimalField(max_digits=10, decimal_places=2, default=0),
                ),
                migrations.AddField(
                    model_name='payment',
                    name='application_fee_amount',
                    field=models.DecimalField(max_digits=10, decimal_places=2, default=0),
                ),
            ],
        )
    ]
