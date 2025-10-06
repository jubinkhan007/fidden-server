from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0008_alter_balance_paid_type'),
        ('payments', '0009_fix_deposit_amount_default'),
    ]

    operations = []
