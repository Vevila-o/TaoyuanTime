from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0003_activity_ticket_free"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="ocr_ready",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activity",
            name="ocr_image_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="activity",
            name="ocr_image_path",
            field=models.CharField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="activity",
            name="ocr_text",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="ocr_summary",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="ocr_confidence",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="ocr_status",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="activity",
            name="ocr_warnings",
            field=models.TextField(blank=True),
        ),
    ]
