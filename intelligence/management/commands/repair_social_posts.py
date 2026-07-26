"""
Commande : réparation des données sociales incohérentes.

Usage :
    python manage.py repair_social_posts
    python manage.py repair_social_posts --post-id 170
"""

from django.core.management.base import BaseCommand

from intelligence.services.social_comment_service import SocialCommentService


class Command(BaseCommand):
    help = 'Répare comments_scraped_count et resynchronise SocialComment depuis le JSON.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=500, help='Nombre max de posts TikTok.')
        parser.add_argument('--post-id', type=int, default=None, help='ID SocialPost ciblé.')

    def handle(self, *args, **options):
        if options['post_id']:
            from intelligence.models import SocialPost

            post = SocialPost.objects.filter(pk=options['post_id']).first()
            if not post:
                self.stdout.write(self.style.ERROR(f'Post #{options["post_id"]} introuvable.'))
                return
            expected = len(post.comments or [])
            if post.comments_scraped_count != expected:
                post.comments_scraped_count = expected
                post.save(update_fields=['comments_scraped_count', 'updated_at'])
            sync = SocialCommentService.sync_post_comments(post)
            self.stdout.write(self.style.SUCCESS(
                f'Post #{post.pk} — comments_scraped_count={post.comments_scraped_count}, sync={sync}'
            ))
            return

        repair = SocialCommentService.repair_comments_scraped_count(limit=options['limit'])
        sync = SocialCommentService.sync_all_from_posts(limit=options['limit'])
        self.stdout.write(self.style.SUCCESS(
            f'Réparation terminée — compteurs fixés : {repair["fixed"]}/{repair["checked"]}, '
            f'sync commentaires : {sync}'
        ))
