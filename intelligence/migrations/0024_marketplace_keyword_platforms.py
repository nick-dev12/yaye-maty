# Generated manually — plateformes Jumia/Jiji pour mots-clés marché

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0023_jiji_keyword_help_text'),
    ]

    operations = [
        migrations.AlterField(
            model_name='marketsearchkeyword',
            name='platform',
            field=models.CharField(
                choices=[
                    ('facebook', 'Facebook'),
                    ('tiktok', 'TikTok'),
                    ('jumia', 'Jumia'),
                    ('jiji', 'Jiji'),
                ],
                db_index=True,
                default='tiktok',
                max_length=20,
                verbose_name='Plateforme',
            ),
        ),
        migrations.AlterField(
            model_name='marketsearchkeyword',
            name='max_videos',
            field=models.PositiveSmallIntegerField(
                default=15,
                help_text=(
                    'TikTok/Facebook : vidéos ou posts. '
                    'Jumia : produits par mot-clé. Jiji : annonces par mot-clé.'
                ),
                verbose_name='Volume max par collecte',
            ),
        ),
        migrations.AlterField(
            model_name='marketsearchkeyword',
            name='max_comments',
            field=models.PositiveSmallIntegerField(
                default=20,
                help_text=(
                    'TikTok/Facebook : commentaires/vidéo. '
                    'Jumia : avis/produit (10–20). Jiji : ignoré.'
                ),
                verbose_name='Commentaires / avis',
            ),
        ),
    ]
