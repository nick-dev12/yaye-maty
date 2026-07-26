# Generated manually — structure TikTok scraping

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0013_alter_socialpost_content'),
    ]

    operations = [
        migrations.AddField(
            model_name='socialpost',
            name='comments_scraped_count',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='Nombre de commentaires enregistrés (objectif : 10–20).',
                verbose_name='Commentaires collectés',
            ),
        ),
        migrations.AlterField(
            model_name='socialpost',
            name='comment_count',
            field=models.PositiveIntegerField(
                blank=True,
                help_text=None,
                null=True,
                verbose_name='Commentaires (total plateforme)',
            ),
        ),
        migrations.AlterField(
            model_name='socialpost',
            name='comments',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='10–20 premiers commentaires : text, commented_at, platform_comment_id.',
                verbose_name='Commentaires (JSON)',
            ),
        ),
        migrations.AlterField(
            model_name='socialpost',
            name='content',
            field=models.TextField(
                help_text='Texte principal de la publication — matière pour le NLP.',
                verbose_name='Description (caption)',
            ),
        ),
        migrations.AlterField(
            model_name='socialpost',
            name='hashtags',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Filtrage thématique (#AgricultureSenegal, etc.).',
                verbose_name='Hashtags',
            ),
        ),
        migrations.AlterField(
            model_name='socialpost',
            name='like_count',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Approbation immédiate des utilisateurs.',
                null=True,
                verbose_name='Likes',
            ),
        ),
        migrations.AlterField(
            model_name='socialpost',
            name='platform_post_id',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Identifiant unique TikTok — anti-doublons.',
                max_length=100,
                verbose_name='ID vidéo (video_id)',
            ),
        ),
        migrations.AlterField(
            model_name='socialpost',
            name='published_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Date publication vidéo — pondération fraîcheur tendance.',
                null=True,
                verbose_name='Publié le',
            ),
        ),
        migrations.AlterField(
            model_name='socialpost',
            name='save_count',
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Intention d'achat — indicateur e-commerce crucial.",
                null=True,
                verbose_name='Favoris (saves)',
            ),
        ),
        migrations.AlterField(
            model_name='socialpost',
            name='share_count',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Intérêt communautaire.',
                null=True,
                verbose_name='Partages',
            ),
        ),
        migrations.AlterField(
            model_name='socialpost',
            name='view_count',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Portée / visibilité globale.',
                null=True,
                verbose_name='Vues',
            ),
        ),
        migrations.AlterField(
            model_name='socialcomment',
            name='published_at',
            field=models.DateTimeField(
                blank=True,
                help_text='commented_at — corrélation intérêt / temps.',
                null=True,
                verbose_name='Date du commentaire',
            ),
        ),
        migrations.AlterField(
            model_name='socialcomment',
            name='text',
            field=models.TextField(verbose_name='Texte du commentaire'),
        ),
        migrations.AlterField(
            model_name='marketsearchkeyword',
            name='max_comments',
            field=models.PositiveSmallIntegerField(
                default=20,
                help_text="Objectif : 10 à 20 commentaires pour l'analyse NLP hybride.",
                verbose_name='Commentaires / vidéo',
            ),
        ),
        migrations.AlterField(
            model_name='socialscrapetarget',
            name='max_comments',
            field=models.PositiveSmallIntegerField(
                default=20,
                help_text="Objectif : 10 à 20 commentaires pour l'analyse NLP.",
                verbose_name='Commentaires / vidéo',
            ),
        ),
    ]
