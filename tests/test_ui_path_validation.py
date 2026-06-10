from ui import looks_like_shell_namespace_path


def test_detects_explorer_shell_namespace_path():
    assert looks_like_shell_namespace_path(r"This PC\Trevor's S26 Ultra\Internal storage\syncr") is True


def test_accepts_real_windows_drive_path():
    assert looks_like_shell_namespace_path(r"E:\Music\Android") is False
