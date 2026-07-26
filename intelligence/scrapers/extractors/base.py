from dataclasses import dataclass, field


@dataclass
class ExtractedPost:
    """Publication brute extraite du DOM — alignée spec intelligence marché."""

    content: str
    author: str = ''
    post_url: str = ''
    platform_post_id: str = ''
    hashtags: list = field(default_factory=list)
    view_count: int | None = None
    like_count: int | None = None
    share_count: int | None = None
    save_count: int | None = None
    comment_count: int | None = None
    published_at: str = ''
    comments: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def is_valid(self, min_length: int = 12) -> bool:
        if self.platform_post_id:
            return bool(self.content and len(self.content.strip()) >= 8)
        return bool(self.content and len(self.content.strip()) >= min_length)
