from django.db import migrations, models


def preservar_cancelados(apps, schema_editor):
    Item = apps.get_model("atendimento", "ComandaItem")
    Item.objects.using(schema_editor.connection.alias).filter(status_producao="CANCELADO").update(cancelado=True)


class Migration(migrations.Migration):
    dependencies = [("atendimento", "0013_cupom_desconto")]

    operations = [
        migrations.AddField(
            model_name="comandaitem",
            name="cancelado",
            field=models.BooleanField(default=False, help_text="Marca se o item foi cancelado sem apagar seu histórico."),
        ),
        migrations.RunPython(preservar_cancelados, migrations.RunPython.noop),
        migrations.RemoveIndex(model_name="comandaitem", name="ix_item_comanda_status"),
        migrations.RemoveField(model_name="comandaitem", name="status_producao"),
    ]
