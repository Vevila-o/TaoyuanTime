from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0002_activity_quality"),
    ]

    operations = [
        migrations.AlterField(
            model_name="activity",
            name="fee_type",
            field=models.CharField(
                choices=[
                    ("free", "free"),
                    ("ticket_free", "ticket_free"),
                    ("paid", "paid"),
                    ("unknown", "unknown"),
                ],
                default="unknown",
                max_length=16,
            ),
        ),
    ]
