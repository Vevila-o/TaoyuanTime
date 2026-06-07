from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0010_activity_official_link_checked_at_and_more"),
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
                    ("mixed", "mixed"),
                    ("unknown", "unknown"),
                ],
                default="unknown",
                max_length=16,
            ),
        ),
    ]
