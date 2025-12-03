# Generated manually for api.Consultation

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_multi_niche_support'),
    ]

    operations = [
        migrations.CreateModel(
            name='Consultation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_name', models.CharField(max_length=200)),
                ('customer_email', models.EmailField(max_length=254)),
                ('customer_phone', models.CharField(blank=True, max_length=20)),
                ('date', models.DateField()),
                ('time', models.TimeField()),
                ('duration_minutes', models.IntegerField(default=30)),
                ('status', models.CharField(choices=[('scheduled', 'Scheduled'), ('confirmed', 'Confirmed'), ('completed', 'Completed'), ('cancelled', 'Cancelled'), ('no_show', 'No Show')], default='scheduled', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('design_reference_images', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='consultations', to='api.shop')),
            ],
            options={
                'ordering': ['date', 'time'],
                'unique_together': {('shop', 'date', 'time')},
            },
        ),
        migrations.AddIndex(
            model_name='consultation',
            index=models.Index(fields=['shop', 'date', 'status'], name='api_consult_shop_id_date_status_idx'),
        ),
    ]
