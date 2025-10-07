from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0016_add_tips_amount_column"),  # adjust to your latest
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # DB already has the column
            state_operations=[
                migrations.AddField(
                    model_name="payment",
                    name="total_amount",
                    field=models.DecimalField(max_digits=10, decimal_places=2, default=0),
                ),
            ],
        ),
    ]
