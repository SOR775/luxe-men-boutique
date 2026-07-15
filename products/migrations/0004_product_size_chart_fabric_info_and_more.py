from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_productreview_fit_feedback_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='care_instructions',
            field=models.TextField(blank=True, help_text='Care instructions'),
        ),
        migrations.AddField(
            model_name='product',
            name='fabric_info',
            field=models.TextField(blank=True, help_text='Fabric composition and feel'),
        ),
        migrations.AddField(
            model_name='product',
            name='model_height',
            field=models.CharField(blank=True, help_text="Model height, e.g. 6'1\"", max_length=50),
        ),
        migrations.AddField(
            model_name='product',
            name='model_size_worn',
            field=models.CharField(blank=True, help_text='Model size worn, e.g. M', max_length=20),
        ),
        migrations.AddField(
            model_name='product',
            name='size_chart',
            field=models.TextField(blank=True, help_text='Size chart notes or measurements'),
        ),
    ]
