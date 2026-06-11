from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0014_alter_actionlog_action_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="activity",
            name="item_type",
            field=models.CharField(
                choices=[
                    ("activity", "activity"),
                    ("news", "news"),
                    ("announcement", "announcement"),
                    ("admin_notice", "admin_notice"),
                    ("penalty_list", "penalty_list"),
                    ("venue_notice", "venue_notice"),
                    ("policy", "policy"),
                    ("procurement", "procurement"),
                    ("recruitment", "recruitment"),
                    ("recap", "recap"),
                    ("place_or_resource", "place_or_resource"),
                    ("unknown", "unknown"),
                ],
                default="activity",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="activity",
            name="excluded_from_public",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activity",
            name="exclude_reason",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="activity",
            name="final_state",
            field=models.CharField(
                choices=[
                    ("published", "可上架"),
                    ("needs_data", "待補資料"),
                    ("needs_review", "待審核"),
                    ("inactive", "已下架"),
                    ("non_activity", "非活動"),
                    ("system_excluded", "系統排除"),
                    ("expired", "過期"),
                ],
                default="needs_review",
                max_length=32,
            ),
        ),
    ]
