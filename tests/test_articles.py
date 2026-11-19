import asyncio
import itertools
from types import SimpleNamespace

import discord
import pytest

import article_publish
from article_publish import Draft, RemovedByModerator, post_title, publish, update, webhook_name
from article_render import Part
from database import (
    add_article,
    add_article_panel,
    article_for_panel,
    init_db,
    mark_article_removed,
    update_article,
)
from docx_import import Picture

PNG = Picture(b"PNGDATA", "image/png")
JPG = Picture(b"JPGDATA", "image/jpeg")


class _Response:
    status = 404
    reason = "Not Found"


class FakeMessage:
    def __init__(self, message_id, thread_id, content, files):
        self.id = message_id
        self.channel = SimpleNamespace(id=thread_id)
        self.content = content
        self.attachments = [SimpleNamespace(filename=f.filename) for f in files]


class FakeThread:
    def __init__(self, thread_id, name, tags):
        self.id = thread_id
        self.name = name
        self.tags = tags
        self.archived = False
        self.deleted = False

    async def edit(self, name, applied_tags, archived):
        self.name, self.tags, self.archived = name, [t.id for t in applied_tags], archived

    async def delete(self):
        self.deleted = True


class FakeForum:
    def __init__(self, tag_ids=(11, 12)):
        self.tags = {i: SimpleNamespace(id=i) for i in tag_ids}
        self.threads: dict[int, FakeThread] = {}

    def get_tag(self, tag_id):
        return self.tags.get(tag_id)

    def get_thread(self, thread_id):
        return self.threads.get(thread_id)


class FakeWebhook:
    def __init__(self, forum):
        self.forum = forum
        self.ids = itertools.count(100)
        self.messages: dict[int, FakeMessage] = {}
        self.sent: list[dict] = []
        self.fail_after = None

    async def send(self, content=discord.utils.MISSING, embeds=(), files=(), thread_name=None,
                   applied_tags=(), thread=None, username=None, avatar_url=None,
                   allowed_mentions=None, wait=False):
        if self.fail_after is not None:
            if self.fail_after == 0:
                raise discord.HTTPException(_Response(), "boom")
            self.fail_after -= 1
        if thread is None:
            thread_id = next(self.ids)
            self.forum.threads[thread_id] = FakeThread(thread_id, thread_name, [t.id for t in applied_tags])
        else:
            thread_id = thread.id
        message = FakeMessage(next(self.ids), thread_id, None if content is discord.utils.MISSING else content, files)
        self.messages[message.id] = message
        self.sent.append(dict(username=username, avatar_url=avatar_url, mentions=allowed_mentions, files=[f.filename for f in files]))
        return message

    async def fetch_message(self, message_id, thread):
        if message_id not in self.messages:
            raise discord.NotFound(_Response(), "Unknown Message")
        return self.messages[message_id]

    async def edit_message(self, message_id, content, embeds, attachments, allowed_mentions, thread):
        message = self.messages[message_id]
        message.content = content
        message.attachments = [SimpleNamespace(filename=a.filename) for a in attachments]

    async def delete_message(self, message_id, thread):
        self.messages.pop(message_id)


AUTHOR = SimpleNamespace(display_name="Coach Discord", display_avatar=SimpleNamespace(url="https://cdn/a.png"))


def draft(*items, cover=PNG, tags=(11,), title="Big win"):
    parts = [Part(image_url=i) if i.startswith("docx-image:") else Part(content=i) for i in items]
    return Draft(title=title, parts=parts, pictures=[JPG, PNG], cover=cover, tags=list(tags))


def run(coro):
    return asyncio.run(coro)


def setup():
    forum = FakeForum()
    return forum, FakeWebhook(forum)


def texts(hook, ids):
    return [hook.messages[i].content or hook.messages[i].attachments[0].filename for i in ids]


# ---------- publishing ----------


def test_publish_creates_a_titled_tagged_post_with_the_cover_first():
    forum, hook = setup()
    thread_id, ids = run(publish(hook, forum, draft("Intro", "docx-image:0", "More"), AUTHOR))
    thread = forum.threads[thread_id]
    assert (thread.name, thread.tags) == ("Big win", [11])
    assert hook.messages[ids[0]].attachments[0].filename == "cover.png"
    assert texts(hook, ids) == ["Intro", "picture.jpg", "More"]


def test_every_message_is_under_the_writer_and_pings_nobody():
    forum, hook = setup()
    run(publish(hook, forum, draft("a", "b"), AUTHOR))
    for sent in hook.sent:
        assert sent["username"] == "Coach Disc0rd"  # webhooks can't say "discord"
        assert sent["avatar_url"] == "https://cdn/a.png"
        assert sent["mentions"].to_dict() == {"parse": []}


def test_unknown_tags_are_ignored():
    forum, hook = setup()
    thread_id, _ = run(publish(hook, forum, draft("a", tags=(11, 99)), AUTHOR))
    assert forum.threads[thread_id].tags == [11]


def test_failure_midway_takes_the_half_post_down():
    forum, hook = setup()
    hook.fail_after = 1
    with pytest.raises(discord.HTTPException):
        run(publish(hook, forum, draft("a", "b", "c"), AUTHOR))
    assert all(t.deleted for t in forum.threads.values())


def test_titles_are_trimmed_to_discords_limit():
    assert post_title("  Pitt   wins ") == "Pitt wins"
    assert len(post_title("x" * 300)) == 100
    assert webhook_name("  ") == "Writer"


# ---------- updating ----------


def test_update_edits_in_place_adds_and_retitles():
    forum, hook = setup()
    thread_id, ids = run(publish(hook, forum, draft("one", "two"), AUTHOR))
    thread = forum.threads[thread_id]
    thread.archived = True
    new_ids = run(update(hook, forum, thread, ids, draft("ONE", "TWO", "THREE", cover=None, tags=(12,), title="New"), AUTHOR))
    assert new_ids[:2] == ids
    assert texts(hook, new_ids) == ["ONE", "TWO", "THREE"]
    assert (thread.name, thread.tags, thread.archived) == ("New", [12], False)


def test_update_without_a_new_picture_keeps_the_old_cover():
    forum, hook = setup()
    thread_id, ids = run(publish(hook, forum, draft("one"), AUTHOR))
    run(update(hook, forum, forum.threads[thread_id], ids, draft("one v2", cover=None), AUTHOR))
    assert [a.filename for a in hook.messages[ids[0]].attachments] == ["cover.png"]


def test_update_with_a_new_picture_replaces_the_cover():
    forum, hook = setup()
    thread_id, ids = run(publish(hook, forum, draft("one"), AUTHOR))
    run(update(hook, forum, forum.threads[thread_id], ids, draft("one", cover=JPG), AUTHOR))
    assert [a.filename for a in hook.messages[ids[0]].attachments] == ["cover.jpg"]


def test_shorter_version_deletes_the_extra_messages():
    forum, hook = setup()
    thread_id, ids = run(publish(hook, forum, draft("a", "b", "c"), AUTHOR))
    new_ids = run(update(hook, forum, forum.threads[thread_id], ids, draft("a"), AUTHOR))
    assert new_ids == ids[:1]
    assert set(hook.messages) == {ids[0]}


def test_post_deleted_by_a_mod_is_never_reposted():
    forum, hook = setup()
    _, ids = run(publish(hook, forum, draft("a"), AUTHOR))
    before = len(hook.sent)
    with pytest.raises(RemovedByModerator):
        run(update(hook, forum, None, ids, draft("a"), AUTHOR))  # thread is gone
    assert len(hook.sent) == before


def test_one_message_deleted_by_a_mod_also_counts_as_removed():
    forum, hook = setup()
    thread_id, ids = run(publish(hook, forum, draft("a", "b"), AUTHOR))
    del hook.messages[ids[1]]
    before = len(hook.sent)
    with pytest.raises(RemovedByModerator):
        run(update(hook, forum, forum.threads[thread_id], ids, draft("a", "b"), AUTHOR))
    assert len(hook.sent) == before
    assert hook.messages[ids[0]].content == "a"  # nothing edited either


# ---------- database ----------


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


def test_article_records_and_panels(db):
    article_id = add_article(db, 7, "Title", [11], 500, [1, 2])
    add_article_panel(db, 900, article_id)
    add_article_panel(db, 901, article_id)  # the panel after an update

    for panel in (900, 901):
        found = article_for_panel(db, panel)
        assert found is not None
        assert (found.author_id, found.thread_id, found.message_ids, found.status) == (7, 500, [1, 2], "published")
    assert article_for_panel(db, 123) is None

    update_article(db, article_id, "New", [12], [1, 2, 3])
    found = article_for_panel(db, 900)
    assert found and (found.title, found.tags, found.message_ids) == ("New", [12], [1, 2, 3])

    mark_article_removed(db, article_id)
    found = article_for_panel(db, 901)
    assert found and found.status == "removed"


def test_cover_file_names():
    assert article_publish._cover_file(JPG).filename == "cover.jpg"
    assert article_publish._cover_file(PNG).filename == "cover.png"


def test_leftover_buttons_after_a_restart_explain_themselves():
    from cogs.articles import EXPIRED, PANEL_IDS, ExpiredArticlePanel

    async def scenario():
        view = ExpiredArticlePanel()
        assert sorted(getattr(i, "custom_id") for i in view.children) == sorted(PANEL_IDS)
        sent, edited = [], []

        async def send_message(text, ephemeral):
            sent.append((text, ephemeral))

        async def edit(view):
            edited.append(view)

        interaction = SimpleNamespace(
            response=SimpleNamespace(send_message=send_message),
            message=SimpleNamespace(edit=edit),
        )
        await view.expired(interaction)
        return sent, edited

    sent, edited = run(scenario())
    assert sent == [(EXPIRED, True)]
    assert edited == [None]


def test_live_panel_uses_the_same_button_ids():
    from cogs.articles import PANEL_IDS, ArticlePanel

    ids = {
        getattr(ArticlePanel, name).__discord_ui_model_kwargs__["custom_id"]
        for name in ArticlePanel.__view_children_items__
    }
    assert ids | {"article:tags"} == set(PANEL_IDS)
