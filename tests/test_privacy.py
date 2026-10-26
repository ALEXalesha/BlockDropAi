"""Личное не публикуется: почта автора, адрес домашнего Gitea, личные пути - ни в одном
файле репозитория. Почта и адрес берутся из настроек git, а не пишутся строкой: иначе
проверка сама стала бы утечкой."""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_HOSTS = ("github.com", "gitlab.com", "codeberg.org")


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def tracked_files():
    # и новые файлы, ещё не добавленные в git: иначе проверка до коммита их не видит
    out = git("ls-files", "--cached", "--others", "--exclude-standard")
    if not out:
        pytest.skip("нет git")
    return [f for f in out.splitlines() if not f.endswith((".npz", ".png", ".ico"))]


def test_no_private_strings_in_tracked_files():
    secrets = []
    email = git("config", "user.email")
    if email:
        secrets.append(re.escape(email))
    origin = git("remote", "get-url", "origin")
    m = re.match(r"^[a-z]+://([^/]+)/", origin)
    # домашний сервер - личное; github.com в клоне с GitHub - нет (на него ссылаются
    # значки README и скрипт выкладки), так же, как в DurakAi
    if m and not m.group(1).lower().endswith(PUBLIC_HOSTS):
        secrets.append(re.escape(m.group(1)))
    secrets.append(re.escape("Drive" + "\\" + "Alexey"))
    secrets.append(re.escape("Drive" + "/" + "Alexey"))
    pattern = re.compile("|".join(secrets), re.IGNORECASE)
    bad = []
    for f in tracked_files():
        path = os.path.join(ROOT, f)
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        if pattern.search(text):
            bad.append(f)
    assert not bad, bad


# spec §0: товарный знак не публикуется. Исключения - описание и план (docs/spec.md,
# docs/plan.md): там разобрано само название, и в публикацию на GitHub они не идут -
# tools/publish.conf (DROP_PATHS) вырезает их из всей истории.
NOT_PUBLISHED = ("docs/spec.md", "docs/plan.md")


def test_no_trademark_in_published_files():
    word = re.compile("tet" + "ris", re.IGNORECASE)
    bad = []
    for f in tracked_files():
        if f in NOT_PUBLISHED:
            continue
        path = os.path.join(ROOT, f)
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        if word.search(text) or word.search(f):
            bad.append(f)
    assert not bad, bad


def test_publish_script_cuts_unpublished_docs():
    src = open(os.path.join(ROOT, "tools", "publish.conf"), encoding="utf-8").read()
    for f in NOT_PUBLISHED:
        assert f in src


def test_public_origin_is_not_a_secret(monkeypatch):
    """В клоне с GitHub origin - github.com, а он законно есть в README и tools/:
    проверка не должна краснеть на CI GitHub."""
    real = git

    def fake(*args):
        if args[0] == "remote":
            return "https://github.com/someone/BlockDropAi.git"
        if args[0] == "config":
            return ""
        return real(*args)
    monkeypatch.setattr(sys.modules[__name__], "git", fake)
    test_no_private_strings_in_tracked_files()
