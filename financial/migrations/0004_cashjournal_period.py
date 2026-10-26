from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("financial", "0003_cash_journal"),
    ]

    operations = [
        migrations.AddField(
            model_name="cashjournal",
            name="period_start",
            field=models.DateField(blank=True, null=True, verbose_name="Période du"),
        ),
        migrations.AddField(
            model_name="cashjournal",
            name="period_end",
            field=models.DateField(blank=True, null=True, verbose_name="Période au"),
        ),
    ]
