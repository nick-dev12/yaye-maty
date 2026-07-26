"""Structure enrichie des publications scrapées (ID, hashtags, commentaires)."""

from django.db import migrations, models


def backfill_platform_post_ids(apps, schema_editor):
    SocialPost = apps.get_model('intelligence', 'SocialPost')
    import re

    for post in SocialPost.objects.filter(platform_post_id='').exclude(post_url=''):
        match = re.search(r'/video/(\d+)', post.post_url or '')
        if match:
            post.platform_post_id = match.group(1)
            post.save(update_fields=['platform_post_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('intelligence', '0010_wolof_keyword'),
    ]

    operations = [
        migrations.AddField(
            model_name='socialpost',
            name='platform_post_id',
            field=models.CharField(blank=True, db_index=True, max_length=100, verbose_name='ID publication'),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='hashtags',
            field=models.JSONField(blank=True, default=list, verbose_name='Hashtags'),
        ),
        migrations.AddField(
            model_name='socialcomment',
            name='platform_comment_id',
            field=models.CharField(blank=True, db_index=True, max_length=100, verbose_name='ID commentaire'),
        ),
        migrations.AddField(
            model_name='socialcomment',
            name='published_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Publié le'),
        ),
        migrations.AddConstraint(
            model_name='socialpost',
            constraint=models.UniqueConstraint(
                condition=models.Q(('platform_post_id__gt', '')),
                fields=('platform', 'platform_post_id'),
                name='unique_social_post_platform_id',
            ),
        ),
        migrations.AddConstraint(
            model_name='socialcomment',
            constraint=models.UniqueConstraint(
                condition=models.Q(('platform_comment_id__gt', '')),
                fields=('post', 'platform_comment_id'),
                name='unique_social_comment_platform_id',
            ),
        ),
        migrations.RunPython(backfill_platform_post_ids, migrations.RunPython.noop),
    ]
