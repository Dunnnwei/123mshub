import pytest

from mshub.errors import ValidationError
from mshub.urltool import mirror_url, parse_source, safe_dir_name


def test_parse_short_github_source() -> None:
    source = parse_source("anthropics/skills")
    assert source.name == "anthropics/skills"
    assert source.source_url == "https://github.com/anthropics/skills"
    assert source.ref == "HEAD"


def test_parse_tree_url_with_subdir() -> None:
    source = parse_source("https://github.com/foo/bar/tree/main/skills/pdf")
    assert source.owner == "foo"
    assert source.repo == "bar"
    assert source.ref == "main"
    assert source.subdir == "skills/pdf"


def test_reject_unsupported_or_unsafe_source() -> None:
    with pytest.raises(ValidationError):
        parse_source("https://gitlab.com/foo/bar")
    with pytest.raises(ValidationError):
        parse_source("foo/bar", subdir="../secret")


def test_safe_name_and_mirror_template() -> None:
    assert safe_dir_name("foo", "bar") == "foo__bar"
    assert mirror_url("https://github.com/a/b", "https://proxy/{url}") == (
        "https://proxy/https://github.com/a/b"
    )

