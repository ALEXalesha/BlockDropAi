"""Block Drop AI: падающие блоки и ИИ, который сам научился в них играть.

Вход игры по контракту PythonAiGames: GAME_INFO и create_widget(ctx). Qt загружается
только в create_widget - правила, ИИ и обучение работают без него.
"""
from game.version import VERSION

GAME_INFO = {
    "id": "blockdrop",
    "title": {"ru": "Блоки с ИИ", "en": "Block Drop AI"},
    "summary": {"ru": "Падающие блоки: играйте сами, смотрите, как играет ИИ, или сразитесь с ним",
                "en": "Falling blocks: play yourself, watch a self-taught AI, or duel it"},
    "preview": "docs/preview.png",
    "version": VERSION,
}

APP_NAME = "BlockDropAi"


def create_widget(ctx):
    """ctx: aikit.Context. Виджет с меню, полем и панелями."""
    from game.ui.widget import GameWidget
    return GameWidget(ctx)
