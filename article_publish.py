"""Post an article to the news forum, or update one already there.

An article becomes one forum post. The first message carries the card
picture as its first attachment (Discord shows that on the forum card), and
each rendered Part is one message: text, or a picture attached as a file.
Every message goes through a webhook so it shows under the writer's name and
avatar, and none of them can ping anyone.

A moderator removes an article by deleting the post (or any message in it).
update() checks everything is still there before touching it and raises
RemovedByModerator if not, so a removed article is never posted again.
"""

import io
import re
from dataclasses import dataclass, field
from typing import Optional

import discord

from article_render import Part
from docx_import import Picture, picture_index

WEBHOOK_NAME = "Articles"
TITLE_MAX = 100
TAGS_MAX = 5
NO_PINGS = discord.AllowedMentions.none()
COVER_PREFIX = "cover."


class RemovedByModerator(Exception):
    pass


@dataclass
class Draft:
    """A submission, converted and ready to post."""

    title: str
    parts: list[Part]
    pictures: list[Picture] = field(default_factory=list)
    cover: Optional[Picture] = None
    tags: list[int] = field(default_factory=list)


def post_title(title: str) -> str:
    title = " ".join(title.split())
    return title if len(title) <= TITLE_MAX else title[: TITLE_MAX - 1] + "…"


def webhook_name(name: str) -> str:
    """Webhook names can't contain 'discord' or 'clyde' and are 1-80 chars."""
    name = re.sub(r"(?i)discord", "Disc0rd", name)
    name = re.sub(r"(?i)clyde", "Clyd3", name).strip()[:80]
    return name or "Writer"


def _file(picture: Picture, filename: Optional[str] = None) -> discord.File:
    # A discord.File is used up once sent, so build a fresh one every time.
    return discord.File(io.BytesIO(picture.data), filename=filename or picture.filename)


def _cover_file(picture: Picture) -> discord.File:
    return _file(picture, COVER_PREFIX + picture.filename.rsplit(".", 1)[-1])


def _part_file(part: Part, draft: Draft) -> Optional[discord.File]:
    index = picture_index(part.image_url)
    if index is None or index >= len(draft.pictures):
        return None
    return _file(draft.pictures[index])


def _part_embeds(part: Part) -> list[discord.Embed]:
    # A picture that's a web address rather than one from the Word file.
    if part.image_url and part.image_url.startswith("https://"):
        return [discord.Embed().set_image(url=part.image_url)]
    return []


async def article_webhook(forum: discord.ForumChannel, bot_user: discord.abc.User) -> discord.Webhook:
    """The bot's own webhook in the forum, created the first time."""
    for hook in await forum.webhooks():
        if hook.user and hook.user.id == bot_user.id and hook.name == WEBHOOK_NAME and hook.token:
            return hook
    return await forum.create_webhook(name=WEBHOOK_NAME, reason="Posting articles from Word files")


async def publish(
    webhook: discord.Webhook,
    forum: discord.ForumChannel,
    draft: Draft,
    author: discord.Member,
) -> tuple[int, list[int]]:
    """Create the forum post. Returns (thread id, message ids)."""
    username = webhook_name(author.display_name)
    avatar_url = author.display_avatar.url
    first = draft.parts[0]
    files = [_cover_file(draft.cover)] if draft.cover else []
    part_file = _part_file(first, draft)
    if part_file:
        files.append(part_file)
    tags = [t for t in (forum.get_tag(i) for i in draft.tags[:TAGS_MAX]) if t]
    message = await webhook.send(
        content=first.content or discord.utils.MISSING,
        embeds=_part_embeds(first),
        files=files,
        thread_name=post_title(draft.title),
        applied_tags=tags,
        username=username,
        avatar_url=avatar_url,
        allowed_mentions=NO_PINGS,
        wait=True,
    )
    thread_id = message.channel.id
    ids = [message.id]
    try:
        for part in draft.parts[1:]:
            part_file = _part_file(part, draft)
            reply = await webhook.send(
                content=part.content or discord.utils.MISSING,
                embeds=_part_embeds(part),
                files=[part_file] if part_file else [],
                thread=discord.Object(thread_id),
                username=username,
                avatar_url=avatar_url,
                allowed_mentions=NO_PINGS,
                wait=True,
            )
            ids.append(reply.id)
    except Exception:
        # Don't leave half an article up.
        thread = forum.get_thread(thread_id)
        if thread:
            await thread.delete()
        raise
    return thread_id, ids


async def update(
    webhook: discord.Webhook,
    forum: discord.ForumChannel,
    thread: Optional[discord.Thread],
    message_ids: list[int],
    draft: Draft,
    author: discord.Member,
) -> list[int]:
    """Edit the post to match a new version. thread is None when it can't be
    found (deleted). Returns the new list of message ids."""
    if thread is None:
        raise RemovedByModerator()
    existing: list[discord.WebhookMessage] = []
    for message_id in message_ids:
        try:
            existing.append(await webhook.fetch_message(message_id, thread=thread))
        except discord.NotFound:
            raise RemovedByModerator() from None

    # Quiet forum posts get archived; reopen it so its messages can be edited.
    tags = [t for t in (forum.get_tag(i) for i in draft.tags[:TAGS_MAX]) if t]
    await thread.edit(name=post_title(draft.title), applied_tags=tags, archived=False)

    old_cover = None
    if existing and existing[0].attachments and existing[0].attachments[0].filename.startswith(COVER_PREFIX):
        old_cover = existing[0].attachments[0]

    kept: list[int] = []
    for i, part in enumerate(draft.parts):
        part_file = _part_file(part, draft)
        if i < len(existing):
            attachments: list = [part_file] if part_file else []
            if i == 0:
                cover = _cover_file(draft.cover) if draft.cover else old_cover
                if cover:
                    attachments.insert(0, cover)
            await webhook.edit_message(
                existing[i].id,
                content=part.content or None,
                embeds=_part_embeds(part),
                attachments=attachments,
                allowed_mentions=NO_PINGS,
                thread=thread,
            )
            kept.append(existing[i].id)
        else:
            reply = await webhook.send(
                content=part.content or discord.utils.MISSING,
                embeds=_part_embeds(part),
                files=[part_file] if part_file else [],
                thread=thread,
                username=webhook_name(author.display_name),
                avatar_url=author.display_avatar.url,
                allowed_mentions=NO_PINGS,
                wait=True,
            )
            kept.append(reply.id)
    for message in existing[len(draft.parts) :]:
        await webhook.delete_message(message.id, thread=thread)
    return kept
