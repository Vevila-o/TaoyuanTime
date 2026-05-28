from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='activity',
            name='item_type',
            field=models.CharField(choices=[('activity', 'activity'), ('announcement', 'announcement'), ('recap', 'recap'), ('place_or_resource', 'place_or_resource')], default='activity', max_length=32),
        ),
        migrations.AddField(
            model_name='activity',
            name='is_activity',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='activity',
            name='is_public_item',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='activity',
            name='line_ready',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='activity',
            name='ai_ready',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='activity',
            name='recommendation_ready',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='activity',
            name='official_detail_url',
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name='activity',
            name='source_key',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='activity',
            name='fee_type',
            field=models.CharField(choices=[('free', 'free'), ('paid', 'paid'), ('unknown', 'unknown')], default='unknown', max_length=10),
        ),
        migrations.AddField(
            model_name='activity',
            name='quality_score',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='activity',
            name='quality_level',
            field=models.CharField(choices=[('high', 'high'), ('medium', 'medium'), ('low', 'low'), ('rejected', 'rejected')], default='medium', max_length=16),
        ),
        migrations.AddField(
            model_name='activity',
            name='quality_warnings',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='activity',
            name='exclude_from_recommendation_reason',
            field=models.TextField(blank=True),
        ),
    ]
