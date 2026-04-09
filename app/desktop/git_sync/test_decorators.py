from app.desktop.git_sync.decorators import no_write_lock, write_lock


def test_write_lock_sets_attribute():
    @write_lock
    def my_endpoint():
        pass

    assert getattr(my_endpoint, "_git_sync_write_lock", False) is True


def test_no_write_lock_sets_attribute():
    @no_write_lock
    def my_endpoint():
        pass

    assert getattr(my_endpoint, "_git_sync_no_write_lock", False) is True


def test_write_lock_preserves_function():
    @write_lock
    def my_endpoint():
        return 42

    assert my_endpoint() == 42


def test_no_write_lock_preserves_function():
    @no_write_lock
    def my_endpoint():
        return 99

    assert my_endpoint() == 99


def test_undecorated_has_no_attributes():
    def my_endpoint():
        pass

    assert getattr(my_endpoint, "_git_sync_write_lock", False) is False
    assert getattr(my_endpoint, "_git_sync_no_write_lock", False) is False
