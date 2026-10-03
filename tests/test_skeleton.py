import os

import game

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_game_info_follows_contract():
    info = game.GAME_INFO
    assert info["id"] == "blockdrop"
    assert set(info["title"]) == {"ru", "en"} and set(info["summary"]) == {"ru", "en"}
    assert info["version"] == game.VERSION
    assert callable(game.create_widget)


def test_no_trademark_in_public_names():
    """spec §0: слово-товарный знак не появляется ни в названии, ни в описании игры."""
    word = "tet" + "ris"
    texts = list(game.GAME_INFO["title"].values()) + list(game.GAME_INFO["summary"].values())
    texts.append(game.APP_NAME)
    assert not any(word in t.lower() for t in texts)


def test_aikit_is_a_copy_with_version():
    assert open(os.path.join(ROOT, "aikit", "VERSION"), encoding="utf-8").read().strip() == "0.1.0"
