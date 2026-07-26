"""Seed initial du dictionnaire Wolof."""

from django.db import migrations, models


DEFAULT_WOLOF_KEYWORDS = [
    ('ñaata', 'purchase', 'combien'),
    ('naata', 'purchase', 'combien'),
    ('naata la', 'purchase', 'combien coûte'),
    ('begg', 'purchase', 'vouloir'),
    ('bëgg', 'purchase', 'vouloir'),
    ('jënd', 'purchase', 'acheter'),
    ('jend', 'purchase', 'acheter'),
    ('dafa am', 'purchase', 'c\'est disponible'),
    ('am na', 'purchase', 'disponible'),
    ('def ko', 'purchase', 'commande'),
    ('defal ma', 'purchase', 'fais pour moi'),
    ('jox ma', 'purchase', 'donne-moi'),
    ('wut', 'purchase', 'chercher'),
    ('wutal ma', 'purchase', 'trouve-moi'),
    ('prix bi', 'purchase', 'le prix'),
    ('xaalis', 'purchase', 'argent'),
    ('whatsapp bi', 'purchase', 'whatsapp'),
]


def seed_wolof_keywords(apps, schema_editor):
    WolofKeyword = apps.get_model('intelligence', 'WolofKeyword')
    for expression, intent, note in DEFAULT_WOLOF_KEYWORDS:
        WolofKeyword.objects.get_or_create(
            expression=expression,
            intent=intent,
            defaults={'note': note, 'is_active': True},
        )


def unseed_wolof_keywords(apps, schema_editor):
    WolofKeyword = apps.get_model('intelligence', 'WolofKeyword')
    expressions = [row[0] for row in DEFAULT_WOLOF_KEYWORDS]
    WolofKeyword.objects.filter(expression__in=expressions).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0009_social_comment'),
    ]

    operations = [
        migrations.CreateModel(
            name='WolofKeyword',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('expression', models.CharField(max_length=120, verbose_name='Expression')),
                ('intent', models.CharField(choices=[('purchase', "Intention d'achat"), ('info', "Demande d'information"), ('complaint', 'Plainte')], db_index=True, default='purchase', max_length=16, verbose_name='Intention')),
                ('note', models.CharField(blank=True, help_text='Ex. : combien coûte, je veux acheter', max_length=200, verbose_name='Signification (optionnel)')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Actif')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Créé le')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Mis à jour le')),
            ],
            options={
                'verbose_name': 'Mot Wolof',
                'verbose_name_plural': 'Dictionnaire Wolof',
                'ordering': ['intent', 'expression'],
            },
        ),
        migrations.AddConstraint(
            model_name='wolofkeyword',
            constraint=models.UniqueConstraint(fields=('expression', 'intent'), name='unique_wolof_keyword_intent'),
        ),
        migrations.RunPython(seed_wolof_keywords, unseed_wolof_keywords),
    ]
