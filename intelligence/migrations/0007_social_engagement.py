"""Migration : métriques d'engagement et ciblage Sénégal."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0006_seed_social_targets'),
    ]

    operations = [
        migrations.AddField(
            model_name='socialpost',
            name='view_count',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Vues'),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='like_count',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Likes'),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='share_count',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Partages'),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='save_count',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Favoris'),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='comment_count',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Commentaires'),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='demand_score',
            field=models.PositiveIntegerField(db_index=True, default=0, verbose_name='Score demande'),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='purchase_intent_count',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='Intentions achat'),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='published_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Publié le'),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='comments',
            field=models.JSONField(blank=True, default=list, verbose_name='Commentaires'),
        ),
        migrations.AddField(
            model_name='socialscrapetarget',
            name='region',
            field=models.CharField(db_index=True, default='SN', max_length=8, verbose_name='Région cible'),
        ),
        migrations.AddField(
            model_name='socialscrapetarget',
            name='scrape_comments',
            field=models.BooleanField(default=True, verbose_name='Extraire commentaires'),
        ),
        migrations.AddField(
            model_name='socialscrapetarget',
            name='max_comments',
            field=models.PositiveSmallIntegerField(default=20, verbose_name='Max commentaires / vidéo'),
        ),
    ]
