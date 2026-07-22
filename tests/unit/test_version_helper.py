from pginspect._version import get_app_version


def test_get_app_version_returns_nonempty_string():
    version = get_app_version()
    assert isinstance(version, str)
    assert version
    assert " " not in version
