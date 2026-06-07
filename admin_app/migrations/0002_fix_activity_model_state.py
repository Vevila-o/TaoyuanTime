from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin_app', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameModel(
                    old_name='Activtiy',
                    new_name='Activity',
                ),
                migrations.AlterModelTable(
                    name='activity',
                    table='admin_app_activtiy',
                ),
                migrations.AlterField(
                    model_name='activity',
                    name='location',
                    field=models.CharField(blank=True, max_length=200, verbose_name='地點'),
                ),
                migrations.AlterField(
                    model_name='activity',
                    name='status',
                    field=models.CharField(
                        choices=[('active', '已上架'), ('inactive', '已下架'), ('draft', '草稿')],
                        default='draft',
                        max_length=10,
                        verbose_name='狀態',
                    ),
                ),
            ],
        ),
    ]
