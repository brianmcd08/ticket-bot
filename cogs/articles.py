"""Articles: content creators drop a Word file in the submit channel and the
bot posts it to the news forum.

  1. A writer posts a message in the submit channel with a .docx attached,
     plus (optionally) a picture to use on the forum card.
  2. The bot replies with the title, a topic dropdown, and Preview /
     Change title / Publish buttons that only that writer can use.
  3. Publish posts the article in the news forum under the writer's name.
  4. To update it, the writer replies to the bot's "Published" message with
     the new Word file; the same buttons appear, with "Update post".

Who can submit is decided by who can post in the submit channel (make it
private to the content-creator role). Mods take an article down by deleting
the post in the forum; it's never posted again after that.
"""

import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands

import article_publish
from article_publish import Draft, RemovedByModerator
from article_render import render_article, word_count
from database import (
    Article,
    add_article,
    add_article_panel,
    article_for_panel,
    mark_article_removed,
    update_article,
)
from docx_import import SHOWABLE, Picture, UnreadableDocument, import_docx

log = logging.getLogger("ticketbot")

MAX_FILE = 10 * 1024 * 1024
PANEL_TIMEOUT = 30 * 60
PREVIEW_MAX = 10
NEWS_GREEN = discord.Color.green()
OTHER_FORMATS = (".doc", ".pdf", ".pages", ".odt", ".rtf", ".txt", ".gdoc")

SAVE_AS_HINT = (
    "I can only read Word files that end in **.docx**. In Word, choose "
    "**File → Save As → Word Document (.docx)**. From Google Docs, choose "
    "**File → Download → Microsoft Word (.docx)**. Then drop that file here."
)
PERMISSION_HELP = (
    "I couldn't post in the news forum. An admin needs to give me **View "
    "Channel, Create Posts, Send Messages in Posts, Attach Files, Embed "
    "Links, Manage Webhooks** and **Manage Posts** there."
)
REMOVED = (
    "A moderator removed this article from the news forum, so it can't be "
    "updated or posted again. Talk to a moderator if you think that's a mistake."
)


def _thread_url(guild_id: int, thread_id: int) -> str:
    return f"https://discord.com/channels/{guild_id}/{thread_id}"


class ArticlesCog(commands.Cog):
    def __init__(self, bot, db_path, submit_channel_id: Optional[int], forum_channel_id: Optional[int]):
        self.bot = bot
        self.db_path = db_path
        self.submit_channel_id = submit_channel_id
        self.forum_channel_id = forum_channel_id
        self._webhook: Optional[discord.Webhook] = None

    def forum(self) -> Optional[discord.ForumChannel]:
        channel = self.bot.get_channel(self.forum_channel_id) if self.forum_channel_id else None
        return channel if isinstance(channel, discord.ForumChannel) else None

    async def webhook(self, forum: discord.ForumChannel) -> discord.Webhook:
        if self._webhook is None:
            self._webhook = await article_publish.article_webhook(forum, self.bot.user)
        return self._webhook

    async def find_thread(self, thread_id: int) -> Optional[discord.Thread]:
        try:
            channel = await self.bot.fetch_channel(thread_id)
        except discord.NotFound:
            return None
        return channel if isinstance(channel, discord.Thread) else None

    # ---------- a file arrives ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.author.bot
            or not self.submit_channel_id
            or message.channel.id != self.submit_channel_id
            or not message.attachments
        ):
            return
        word = next((a for a in message.attachments if a.filename.lower().endswith(".docx")), None)
        if word is None:
            if any(a.filename.lower().endswith(OTHER_FORMATS) for a in message.attachments):
                await message.reply(SAVE_AS_HINT, mention_author=False)
            return
        try:
            await self.handle_submission(message, word)
        except Exception:
            log.exception("Article submission failed (message %s)", message.id)
            await message.reply(
                "Something went wrong reading that file. It has been logged; please try again.",
                mention_author=False,
            )

    async def handle_submission(self, message: discord.Message, word: discord.Attachment):
        forum = self.forum()
        if forum is None:
            await message.reply(
                "Articles aren't set up yet: I can't find the news forum. Ask an admin.",
                mention_author=False,
            )
            return
        if word.size > MAX_FILE:
            await message.reply(
                "That Word file is over 10 MB, usually because of large pictures. "
                "In Word, use **Compress Pictures**, save, and try again.",
                mention_author=False,
            )
            return

        # Replying to a "Published" message means: update that article.
        article: Optional[Article] = None
        if message.reference and message.reference.message_id:
            article = article_for_panel(self.db_path, message.reference.message_id)
            if article and article.author_id != message.author.id:
                await message.reply(
                    "Only the writer of that article can update it.", mention_author=False
                )
                return
            if article and article.status == "removed":
                await message.reply(REMOVED, mention_author=False)
                return

        try:
            imported = await asyncio.to_thread(import_docx, await word.read(), word.filename)
        except UnreadableDocument:
            await message.reply(
                "I couldn't read that Word file. Open it in Word, choose **File → Save As → "
                "Word Document (.docx)**, and drop the new file here.",
                mention_author=False,
            )
            return

        parts = render_article(imported.doc)
        if not parts:
            await message.reply("That document looks empty, so there's nothing to post.", mention_author=False)
            return

        cover = None
        picture = next(
            (a for a in message.attachments if (a.content_type or "").split(";")[0] in SHOWABLE),
            None,
        )
        if picture is not None:
            cover = Picture(await picture.read(), (picture.content_type or "").split(";")[0])

        draft = Draft(
            title=imported.title,
            parts=parts,
            pictures=imported.pictures,
            cover=cover,
            tags=list(article.tags) if article else [],
        )
        panel = ArticlePanel(self, forum, draft, message.author.id, article, imported.skipped_pictures, word_count(imported.doc))
        panel.message = await message.reply(embed=panel.embed(), view=panel, mention_author=False)


class TagSelect(discord.ui.Select["ArticlePanel"]):
    def __init__(self, forum: discord.ForumChannel, chosen: list[int]):
        tags = [t for t in forum.available_tags if not t.moderated][:25]
        required = forum.flags.require_tag
        super().__init__(
            placeholder="Pick topics" + ("" if required else " (optional)"),
            min_values=0,
            max_values=min(article_publish.TAGS_MAX, len(tags)),
            options=[
                discord.SelectOption(label=t.name, value=str(t.id), emoji=t.emoji, default=t.id in chosen)
                for t in tags
            ],
            row=0,
            custom_id="article:tags",
        )

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        self.view.draft.tags = [int(v) for v in self.values]
        for option in self.options:
            option.default = option.value in self.values
        await interaction.response.edit_message(embed=self.view.embed(), view=self.view)


class TitleModal(discord.ui.Modal, title="Change the title"):
    def __init__(self, panel: "ArticlePanel"):
        super().__init__()
        self.panel = panel
        self.field = discord.ui.TextInput(
            label="Title",
            default=panel.draft.title[: article_publish.TITLE_MAX],
            max_length=article_publish.TITLE_MAX,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        self.panel.draft.title = self.field.value.strip() or self.panel.draft.title
        await interaction.response.edit_message(embed=self.panel.embed(), view=self.panel)


class ArticlePanel(discord.ui.View):
    def __init__(
        self,
        cog: ArticlesCog,
        forum: discord.ForumChannel,
        draft: Draft,
        author_id: int,
        article: Optional[Article],
        skipped_pictures: int,
        words: int,
    ):
        super().__init__(timeout=PANEL_TIMEOUT)
        self.cog = cog
        self.forum = forum
        self.draft = draft
        self.author_id = author_id
        self.article = article
        self.skipped = skipped_pictures
        self.words = words
        self.message: Optional[discord.Message] = None
        self.busy = False
        if any(not t.moderated for t in forum.available_tags):
            self.add_item(TagSelect(forum, draft.tags))
        if article:
            self.publish.label = "Update post"

    def embed(self) -> discord.Embed:
        d = self.draft
        pictures = sum(1 for p in d.parts if p.image_url)
        lines = [
            f"📄 {self.words:,} words · {len(d.parts)} message{'s' if len(d.parts) != 1 else ''}"
            + (f" · {pictures} picture{'s' if pictures != 1 else ''}" if pictures else ""),
            "🖼️ Card picture: **yes**, the picture you attached"
            if d.cover
            else "🖼️ Card picture: none. To add one, attach a picture along with the Word file.",
        ]
        names = [t.name for t in (self.forum.get_tag(i) for i in d.tags) if t]
        lines.append(f"🏷️ Topics: {', '.join(names) if names else 'none picked'}")
        if self.skipped:
            lines.append(
                f"⚠️ {self.skipped} drawing{'s' if self.skipped != 1 else ''} couldn't be used "
                "(Discord can't show that kind). Use a normal picture (PNG or JPG) instead."
            )
        if self.article:
            lines.append(
                f"\nThis will replace your post: {_thread_url(self.forum.guild.id, self.article.thread_id)}"
            )
        action = "Update post" if self.article else "Publish"
        lines.append(f"\nCheck the title, pick topics, then press **Preview** or **{action}**.")
        return discord.Embed(title=f"📰 {d.title}", description="\n".join(lines), color=NEWS_GREEN)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the writer who sent this file can use these buttons.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(
                    content="These buttons expired. Drop the file again when you're ready.",
                    view=None,
                )
            except discord.HTTPException:
                pass

    async def finish(self, embed: discord.Embed):
        self.stop()
        if self.message:
            await self.message.edit(embed=embed, view=None)

    @discord.ui.button(label="Preview", emoji="👀", style=discord.ButtonStyle.secondary, row=1, custom_id="article:preview")
    async def preview(self, interaction: discord.Interaction, _button: discord.ui.Button):
        d = self.draft
        await interaction.response.send_message(
            f"Preview of **{article_publish.post_title(d.title)}**. Only you can see this.",
            ephemeral=True,
        )
        if d.cover:
            await interaction.followup.send(
                "Card picture:", file=article_publish._cover_file(d.cover), ephemeral=True
            )
        for part in d.parts[:PREVIEW_MAX]:
            part_file = article_publish._part_file(part, d)
            await interaction.followup.send(
                content=part.content or discord.utils.MISSING,
                embeds=article_publish._part_embeds(part),
                file=part_file or discord.utils.MISSING,
                allowed_mentions=article_publish.NO_PINGS,
                ephemeral=True,
            )
        if len(d.parts) > PREVIEW_MAX:
            await interaction.followup.send(
                f"…and {len(d.parts) - PREVIEW_MAX} more message(s).", ephemeral=True
            )

    @discord.ui.button(label="Change title", emoji="✏️", style=discord.ButtonStyle.secondary, row=1, custom_id="article:title")
    async def change_title(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(TitleModal(self))

    @discord.ui.button(label="Publish", emoji="✅", style=discord.ButtonStyle.success, row=1, custom_id="article:publish")
    async def publish(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self.busy:
            await interaction.response.send_message("Already working on it…", ephemeral=True)
            return
        if self.forum.flags.require_tag and not self.draft.tags:
            await interaction.response.send_message("Pick at least one topic first.", ephemeral=True)
            return
        author = interaction.user
        if not isinstance(author, discord.Member):
            await interaction.response.send_message("This only works inside the server.", ephemeral=True)
            return
        self.busy = True
        await interaction.response.defer()
        try:
            await self._post(author)
        except discord.Forbidden:
            log.exception("Missing permissions posting an article")
            self.busy = False
            await interaction.followup.send(PERMISSION_HELP, ephemeral=True)
        except discord.HTTPException:
            log.exception("Discord error posting an article")
            self.busy = False
            await interaction.followup.send(
                "Discord had a problem posting that. Please try again in a minute.", ephemeral=True
            )

    async def _post(self, author: discord.Member):
        cog, d = self.cog, self.draft
        webhook = await cog.webhook(self.forum)
        title = article_publish.post_title(d.title)
        if self.article:
            thread = await cog.find_thread(self.article.thread_id)
            try:
                ids = await article_publish.update(webhook, self.forum, thread, self.article.message_ids, d, author)
            except RemovedByModerator:
                log.info("Article %s was removed by a moderator", self.article.id)
                mark_article_removed(cog.db_path, self.article.id)
                await self.finish(discord.Embed(title=f"🚫 {title}", description=REMOVED, color=discord.Color.red()))
                return
            update_article(cog.db_path, self.article.id, title, d.tags, ids)
            article_id, thread_id = self.article.id, self.article.thread_id
            verb = "Updated"
        else:
            thread_id, ids = await article_publish.publish(webhook, self.forum, d, author)
            article_id = add_article(cog.db_path, author.id, title, d.tags, thread_id, ids)
            verb = "Published"
        log.info("%s article %s (%s) by %s", verb, article_id, title, author.id)
        if self.message:
            add_article_panel(cog.db_path, self.message.id, article_id)
        url = _thread_url(self.forum.guild.id, thread_id)
        await self.finish(
            discord.Embed(
                title=f"✅ {verb}: {title}",
                description=(
                    f"It's live in {self.forum.mention}: {url}\n\n"
                    "To update it later, **reply to this message** with the new Word file."
                ),
                color=NEWS_GREEN,
            )
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1, custom_id="article:cancel")
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.defer()
        await self.finish(
            discord.Embed(description="Cancelled. Nothing was posted.", color=discord.Color.light_grey())
        )


EXPIRED = "These buttons stopped working because the bot restarted. Please drop the Word file again."
PANEL_IDS = ("article:tags", "article:preview", "article:title", "article:publish", "article:cancel")


class ExpiredArticlePanel(discord.ui.View):
    """Answers clicks on a reply left over from before a restart.

    Registered once at startup with no message attached. A live reply's own
    buttons (same custom ids, tied to its message) always take precedence,
    so this only ever sees clicks nobody else is listening for.
    """

    def __init__(self):
        super().__init__(timeout=None)
        for custom_id in PANEL_IDS:
            if custom_id == "article:tags":
                item = discord.ui.Select(custom_id=custom_id, options=[discord.SelectOption(label="-")])
            else:
                item = discord.ui.Button(custom_id=custom_id)
            item.callback = self.expired
            self.add_item(item)

    async def expired(self, interaction: discord.Interaction):
        await interaction.response.send_message(EXPIRED, ephemeral=True)
        if interaction.message is not None:
            try:
                await interaction.message.edit(view=None)
            except discord.HTTPException:
                pass
