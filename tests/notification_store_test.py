from sqlmodel import SQLModel, create_engine

from born_portal.notifications.model import Notification
from born_portal.notifications.routes import linkify
from born_portal.notifications.store import NotificationStore


def make_store(tmp_path) -> NotificationStore:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    return NotificationStore(engine)


def test_save_and_reverse_date_order(tmp_path):
    store = make_store(tmp_path)
    store.add_if_new("First", "a", "2026-01-01")
    store.add_if_new("Second", "b", "2026-02-01")

    assert [n.title for n in store.list_all()] == ["Second", "First"]


def test_add_if_new_deduplicates_by_date_and_title(tmp_path):
    store = make_store(tmp_path)
    first_id, created = store.add_if_new("Hello", "one", "2026-01-01")
    assert created is True

    # Same date and title (case-insensitive) is not duplicated.
    second_id, created = store.add_if_new("  hello ", "two", "2026-01-01")
    assert created is False
    assert second_id == first_id
    assert len(store.list_all()) == 1

    # Same title on a different date is allowed.
    other_id, created = store.add_if_new("Hello", "three", "2026-02-02")
    assert created is True
    assert other_id != first_id
    assert len(store.list_all()) == 2


def test_find_by_date_title(tmp_path):
    store = make_store(tmp_path)
    note_id, _ = store.add_if_new("Title", "body", "2026-03-04")

    found = store.find_by_date_title("2026-03-04", "title")
    assert found is not None
    assert found.id == note_id
    assert store.find_by_date_title("2026-03-05", "Title") is None
    assert store.find_by_date_title("2026-03-04", "Other") is None


def test_save_updates_existing(tmp_path):
    store = make_store(tmp_path)
    note_id, _ = store.add_if_new("Title", "body", "2026-03-04")

    store.save(
        Notification(
            id=note_id,
            title="Edited",
            text="new body",
            created_at="2026-03-04",
            read=True,
        )
    )

    updated = store.get_by_id(note_id)
    assert updated.title == "Edited"
    assert updated.text == "new body"
    assert updated.read is True


def test_mark_read_many_is_idempotent(tmp_path):
    store = make_store(tmp_path)
    a, _ = store.add_if_new("A", "a", "2026-01-01")
    b, _ = store.add_if_new("B", "b", "2026-01-02")
    store.set_read(a)  # already read

    assert store.unread_count() == 1
    assert store.mark_read_many([a, b]) == 1
    assert store.unread_count() == 0
    assert store.mark_read_many([a, b]) == 0
    assert store.mark_read_many([]) == 0


def test_read_and_delete(tmp_path):
    store = make_store(tmp_path)
    note_id, _ = store.add_if_new("N", "t", "2026-01-01")

    assert store.unread_count() == 1
    assert store.set_read(note_id) is True
    assert store.unread_count() == 0
    assert store.get_by_id(note_id).read is True

    assert store.set_read(note_id, False) is True
    assert store.unread_count() == 1

    assert store.delete(note_id) is True
    assert store.get_by_id(note_id) is None
    assert store.delete(note_id) is False


def test_linkify_escapes_and_links():
    rendered = linkify("Hello <b>there</b>\nsee https://example.com/a?b=1&c=2.")

    assert "<b>" not in rendered
    assert "&lt;b&gt;" in rendered
    assert 'href="https://example.com/a?b=1&amp;c=2"' in rendered
    assert "&amp;c=2.</a>" not in rendered  # trailing period stays outside link
    assert rendered.endswith(".")
