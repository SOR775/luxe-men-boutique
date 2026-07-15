from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('wallets', '0002_walletreward_wallettopup'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallettopup',
            name='checkout_request_id',
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AddField(
            model_name='wallettopup',
            name='phone_number',
            field=models.CharField(blank=True, max_length=15),
        ),
    ]
