from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from collections import Counter
from typing import Iterable
import random
import re
import time
import json


# ============================================================
# 基本データ
# ============================================================

COLORS = ("orange", "blue", "pink")

GROUPS: dict[str, tuple[str, ...]] = {
    "JP0": (
        "Tokino Sora", "Roboco-san", "AZKi", "Sakura Miko", "Hoshimachi Suisei",
    ),
    "JP1": (
        "Aki Rosenthal", "Akai Haato", "Shirakami Fubuki", "Natsuiro Matsuri",
    ),
    "JP2": (
        "Murasaki Shion", "Nakiri Ayame", "Yuzuki Choco", "Oozora Subaru",
    ),
    "GAMERS": (
        "Shirakami Fubuki", "Ookami Mio", "Nekomata Okayu", "Inugami Korone",
    ),
    "JP3": (
        "Usada Pekora", "Shiranui Flare", "Shirogane Noel", "Houshou Marine",
    ),
    "JP4": (
        "Amane Kanata", "Tsunomaki Watame", "Tokoyami Towa", "Himemori Luna",
    ),
    "JP5": (
        "Yukihana Lamy", "Momosuzu Nene", "Shishiro Botan", "Omaru Polka",
    ),
    "HOLOX": (
        "La+ Darknesss", "Takane Lui", "Hakui Koyori", "Sakamata Chloe", "Kazama Iroha",
    ),
    "REGLOSS": (
        "Hiodoshi Ao", "Otonose Kanade", "Ichijou Ririka", "Juufuutei Raden", "Todoroki Hajime",
    ),
    "MYTH": (
        "Mori Calliope", "Takanashi Kiara", "Ninomae Ina'nis", "Gawr Gura", "Watson Amelia",
    ),
    "ADVENT": (
        "Shiori Novella", "Koseki Bijou", "Nerissa Ravencroft",
        "Fuwawa Abyssgard", "Mococo Abyssgard",
    ),
    "PROMISE": (
        "IRyS", "Ouro Kronii", "Hakos Baelz", "Ceres Fauna", "Nanashi Mumei",
    ),
    "ID1": (
        "Ayunda Risu", "Moona Hoshinova", "Airani Iofifteen",
    ),
    "ID2": (
        "Kureiji Ollie", "Anya Melfissa", "Pavolia Reine",
    ),
    "ID3": (
        "Vestia Zeta", "Kaela Kovalskia", "Kobo Kanaeru",
    ),
}

INCOMPATIBLE_GROUP_PAIRS = {
    frozenset(("JP1", "GAMERS")),
}

ROLE_BASE_SCORE = {
    ("same_member_3", False): 120,
    ("same_member_3", True): 840,
    ("group_3", False): 180,
    ("group_3", True): 480,
    ("group_4", False): 300,
    ("group_4", True): 840,
    ("group_5", False): 480,
    ("group_5", True): 1800,
}

BONUS_PER_CARD = 90


# ============================================================
# データクラス
# ============================================================

@dataclass(frozen=True, slots=True)
class Card:
    member: str
    color: str
    copy_no: int

    def short(self) -> str:
        c = {"orange": "橙", "blue": "青", "pink": "桃"}[self.color]
        return f"{self.member}[{c}{self.copy_no}]"


@dataclass(frozen=True, slots=True)
class Role:
    kind: str
    group: str | None
    cards: tuple[Card, ...]
    same_color: bool
    base_score: int
    bonus_count: int
    total_score: int

    def label(self) -> str:
        if self.kind == "same_member_3":
            name = f"{self.cards[0].member}×3"
        else:
            name = f"{self.group} {len(self.cards)}人組"
        color = "同色" if self.same_color else "異色"
        bonus = f" +ボーナス{self.bonus_count}枚" if self.bonus_count else ""
        return f"{name} / {color} / {self.total_score}点{bonus}"


@dataclass
class Player:
    name: str
    coins: int = 3000
    hand: list[Card] = field(default_factory=list)


@dataclass
class GameResult:
    winner_names: list[str]
    final_coins: dict[str, int]
    turns: int
    end_reason: str


# ============================================================
# 山札生成
# ============================================================

def groups_are_compatible(groups: Iterable[str]) -> bool:
    s = set(groups)
    return all(not pair.issubset(s) for pair in INCOMPATIBLE_GROUP_PAIRS)


def select_four_groups(rng: random.Random) -> tuple[str, ...]:
    names = tuple(GROUPS)
    valid = [combo for combo in combinations(names, 4) if groups_are_compatible(combo)]
    return rng.choice(valid)


def members_in_groups(selected_groups: Iterable[str]) -> tuple[str, ...]:
    seen = set()
    members = []
    for group in selected_groups:
        for member in GROUPS[group]:
            if member not in seen:
                seen.add(member)
                members.append(member)
    return tuple(members)


def make_full_card_pool(selected_groups: Iterable[str]) -> list[Card]:
    pool: list[Card] = []
    for member in members_in_groups(selected_groups):
        for color in COLORS:
            for copy_no in range(1, 4):
                pool.append(Card(member, color, copy_no))
    return pool


def make_100_card_deck(
    selected_groups: Iterable[str],
    rng: random.Random,
) -> tuple[list[Card], list[Card]]:
    pool = make_full_card_pool(selected_groups)

    if len(pool) < 100:
        raise ValueError(
            f"候補カードが{len(pool)}枚しかなく、100枚山札を作れません。"
        )

    rng.shuffle(pool)
    return pool[:100], pool[100:]


# ============================================================
# 役判定
# ============================================================

def _all_same_color(cards: Iterable[Card]) -> bool:
    cards = tuple(cards)
    return len({c.color for c in cards}) == 1


def _is_valid_non_same_color(cards: tuple[Card, ...]) -> bool:
    """
    暫定仕様:
    - 3枚役: 3色すべて異なる場合のみ「異なる色」役
    - 4/5枚役: 全部同色でなければ「異なる色」役

    同色役は、枚数に関係なく全カードが完全に同じ色のときだけ成立。
    """
    if _all_same_color(cards):
        return False

    if len(cards) == 3:
        return len({c.color for c in cards}) == 3

    return True


def _score_role(
    kind: str,
    cards: tuple[Card, ...],
    bonus_member: str,
) -> tuple[int, int, int]:
    same = _all_same_color(cards)

    if kind == "same_member_3":
        key = ("same_member_3", same)
    else:
        key = (f"group_{len(cards)}", same)

    base = ROLE_BASE_SCORE[key]
    bonus_count = sum(c.member == bonus_member for c in cards)
    total = base + BONUS_PER_CARD * bonus_count
    return base, bonus_count, total


def find_roles(
    hand: Iterable[Card],
    active_groups: Iterable[str],
    bonus_member: str,
) -> list[Role]:
    cards = tuple(hand)
    roles: list[Role] = []

    # --------------------------------------------------------
    # 同じホロメン3枚
    # --------------------------------------------------------
    by_member: dict[str, list[Card]] = {}
    for c in cards:
        by_member.setdefault(c.member, []).append(c)

    for member, member_cards in by_member.items():
        if len(member_cards) < 3:
            continue

        for chosen in combinations(member_cards, 3):
            chosen = tuple(chosen)
            same = _all_same_color(chosen)

            if not same and not _is_valid_non_same_color(chosen):
                continue

            base, bonus_count, total = _score_role(
                "same_member_3", chosen, bonus_member
            )

            roles.append(Role(
                kind="same_member_3",
                group=None,
                cards=chosen,
                same_color=same,
                base_score=base,
                bonus_count=bonus_count,
                total_score=total,
            ))

    # --------------------------------------------------------
    # グループ役
    # --------------------------------------------------------
    for group in active_groups:
        member_names = GROUPS[group]
        n = len(member_names)

        if n not in (3, 4, 5):
            raise ValueError(f"未対応のグループ人数です: {group}={n}")

        choices_by_member: list[list[Card]] = []

        for member in member_names:
            choices = [c for c in cards if c.member == member]
            if not choices:
                break
            choices_by_member.append(choices)
        else:
            combos = [()]
            for choices in choices_by_member:
                combos = [prev + (c,) for prev in combos for c in choices]

            for chosen in combos:
                same = _all_same_color(chosen)

                if not same and not _is_valid_non_same_color(chosen):
                    continue

                kind = f"group_{n}"
                base, bonus_count, total = _score_role(
                    kind, chosen, bonus_member
                )

                roles.append(Role(
                    kind=kind,
                    group=group,
                    cards=chosen,
                    same_color=same,
                    base_score=base,
                    bonus_count=bonus_count,
                    total_score=total,
                ))

    # 重複除去
    unique: dict[tuple, Role] = {}
    for r in roles:
        key = (
            r.kind,
            r.group,
            tuple(sorted((c.member, c.color, c.copy_no) for c in r.cards)),
        )
        unique[key] = r

    return sorted(
        unique.values(),
        key=lambda r: (r.total_score, len(r.cards)),
        reverse=True,
    )


def roles_completed_by_discard(
    hand: Iterable[Card],
    discarded_card: Card,
    active_groups: Iterable[str],
    bonus_member: str,
) -> list[Role]:
    roles = find_roles(
        list(hand) + [discarded_card],
        active_groups,
        bonus_member,
    )
    return [role for role in roles if discarded_card in role.cards]


# ============================================================
# ランダムAI
# ============================================================

class RandomAgent:
    """
    最初の基準AI。
    - 役があればランダムに1つ宣言
    - 打牌もランダム
    """

    def choose_self_draw_role(
        self,
        game: "PokaJanGame",
        player_index: int,
        roles: list[Role],
    ) -> Role | None:
        if not roles:
            return None
        return game.rng.choice(roles)

    def choose_discard_claim(
        self,
        game: "PokaJanGame",
        player_index: int,
        roles: list[Role],
    ) -> Role | None:
        if not roles:
            return None
        return game.rng.choice(roles)

    def choose_discard(
        self,
        game: "PokaJanGame",
        player_index: int,
    ) -> Card:
        return game.rng.choice(game.players[player_index].hand)


# ============================================================
# ゲーム本体
# ============================================================

class PokaJanGame:
    def __init__(
        self,
        seed: int | None = None,
        starting_coins: int = 1000,
        selected_groups: tuple[str, ...] | None = None,
        agents: list[RandomAgent] | None = None,
        verbose: bool = False,
    ):
        self.rng = random.Random(seed)
        self.verbose = verbose

        self.selected_groups = (
            selected_groups
            if selected_groups is not None
            else select_four_groups(self.rng)
        )

        if len(self.selected_groups) != 4:
            raise ValueError("選択グループは4組である必要があります。")

        if not groups_are_compatible(self.selected_groups):
            raise ValueError("JP1とGAMERSは同時選出できません。")

        self.active_members = members_in_groups(self.selected_groups)
        self.bonus_member = self.rng.choice(self.active_members)

        deck, unused = make_100_card_deck(self.selected_groups, self.rng)
        self.deck = deck
        self.unused_cards = unused

        self.discards: list[Card] = []

        self.players = [
            Player(f"P{i+1}", starting_coins)
            for i in range(4)
        ]

        self.agents = agents or [RandomAgent() for _ in range(4)]
        if len(self.agents) != 4:
            raise ValueError("AIは4人分必要です。")

        self.turn_index = 0
        self.turn_count = 0

        for p in self.players:
            self.draw_cards(p, 7)

    # --------------------------------------------------------
    # ログ
    # --------------------------------------------------------

    def log(self, text: str = "") -> None:
        if self.verbose:
            print(text)

    # --------------------------------------------------------
    # 基本操作
    # --------------------------------------------------------

    def draw_cards(self, player: Player, n: int = 1) -> list[Card]:
        drawn = []
        for _ in range(n):
            if not self.deck:
                break
            c = self.deck.pop()
            player.hand.append(c)
            drawn.append(c)
        return drawn

    def remove_role_cards_from_hand(
        self,
        player: Player,
        role: Role,
        external_card: Card | None = None,
    ) -> None:
        """
        external_card は相手の捨て牌。
        それだけは手札に存在しないので除外して削除する。
        """
        pending = list(role.cards)

        if external_card is not None:
            pending.remove(external_card)

        for c in pending:
            player.hand.remove(c)

    # --------------------------------------------------------
    # 支払い
    # --------------------------------------------------------

    def pay_self_draw_role(self, winner_index: int, score: int) -> None:
        if score % 3 != 0:
            raise ValueError(f"{score}点は3等分できません。")

        share = score // 3
        winner = self.players[winner_index]

        # 勝者は役の満額を受け取る。
        winner.coins += score

        # 支払う側は0未満にはならない。
        for i, loser in enumerate(self.players):
            if i == winner_index:
                continue

            loser.coins = max(0, loser.coins - share)

    def pay_discard_role(
        self,
        winner_index: int,
        discarder_index: int,
        score: int,
    ) -> None:
        winner = self.players[winner_index]
        loser = self.players[discarder_index]

        # 勝者は役の満額を受け取る。
        winner.coins += score

        # 支払う側は0未満にはならない。
        loser.coins = max(0, loser.coins - score)

    # --------------------------------------------------------
    # 役宣言
    # --------------------------------------------------------

    def resolve_self_draw_roles(self, player_index: int) -> None:
        """
        自分のターンで役があれば、AIが役を選び宣言。
        宣言後の補充で再び役が成立する可能性があるため、
        宣言し続けられる限り繰り返す。
        """
        player = self.players[player_index]
        agent = self.agents[player_index]

        while self.deck and player.coins > 0:
            roles = find_roles(
                player.hand,
                self.selected_groups,
                self.bonus_member,
            )

            if not roles:
                break

            chosen = agent.choose_self_draw_role(self, player_index, roles)
            if chosen is None:
                break

            self.log(
                f"{player.name} 自摸役: {chosen.label()}"
            )

            self.remove_role_cards_from_hand(player, chosen)
            self.pay_self_draw_role(player_index, chosen.total_score)

            self.draw_cards(player, len(chosen.cards))

            if self.is_finished():
                break

    def resolve_replacement_draws(
        self,
        player_index: int,
        draw_count: int,
    ) -> None:
        """
        他人の捨て牌で上がった後の補充を処理する。

        重要な考え方:
        - 自分のターン以外の通常手札は7枚固定。
        - 補充で引いた1枚が役を完成させた場合、その1枚を
          「上がり牌（外部カード）」として扱う。
        - したがって手札から消費するのは役枚数-1枚。
        - その役の後も役枚数-1枚を追加補充する。
        - これを成立する限り何回でも繰り返す。

        補充牌が役を完成させなければ、そのカードを通常手札に加える。
        """
        player = self.players[player_index]
        agent = self.agents[player_index]

        pending_draws = draw_count

        while (
            pending_draws > 0
            and self.deck
            and player.coins > 0
        ):
            # 補充牌を1枚引く。ただし、役判定が終わるまでは
            # 通常手札には加えず「外部の上がり牌」として扱う。
            drawn_card = self.deck.pop()
            pending_draws -= 1

            roles = roles_completed_by_discard(
                player.hand,
                drawn_card,
                self.selected_groups,
                self.bonus_member,
            )

            if not roles:
                # 上がれなければ普通に手札へ入る。
                player.hand.append(drawn_card)
                continue

            chosen = agent.choose_discard_claim(
                self,
                player_index,
                roles,
            )

            if chosen is None:
                player.hand.append(drawn_card)
                continue

            self.log(
                f"{player.name} 補充牌で連続役: "
                f"{chosen.label()} / trigger={drawn_card.short()}"
            )

            # drawn_card は外部の上がり牌なので、
            # 自分の手札から消すのは役枚数-1枚だけ。
            self.remove_role_cards_from_hand(
                player,
                chosen,
                external_card=drawn_card,
            )

            # 補充牌で自力成立した役として、現時点では
            # 3人均等払いを維持する。
            self.pay_self_draw_role(
                player_index,
                chosen.total_score,
            )

            # 今の役によって、さらに「役枚数-1枚」の補充が発生。
            pending_draws += len(chosen.cards) - 1

            if self.is_finished():
                break

    def resolve_discard_claims(
        self,
        discarder_index: int,
        discarded_card: Card,
    ) -> None:
        """
        捨て牌によって複数人が同時に上がれる場合の正式優先ルール:

        1. 各プレイヤーについて、その捨て牌で作れる役の中から
           そのプレイヤーが選ぶ役を1つ決める。
        2. その中で役の得点が最も高いプレイヤーを優先。
        3. 最高得点が同点なら、捨てた人の次のプレイヤーから
           近い順に優先。
        4. 実際に上がるのは優先された1人だけ。
        """
        if self.is_finished():
            return

        order = [
            (discarder_index + offset) % 4
            for offset in (1, 2, 3)
        ]

        candidates = []

        for seat_priority, winner_index in enumerate(order):
            winner = self.players[winner_index]

            roles = roles_completed_by_discard(
                winner.hand,
                discarded_card,
                self.selected_groups,
                self.bonus_member,
            )

            if not roles:
                continue

            chosen = self.agents[winner_index].choose_discard_claim(
                self,
                winner_index,
                roles,
            )

            if chosen is None:
                continue

            candidates.append(
                (
                    chosen.total_score,
                    seat_priority,
                    winner_index,
                    chosen,
                )
            )

        if not candidates:
            return

        # 得点が最大の候補を取り、同点ならseat_priority最小を採用。
        candidates.sort(
            key=lambda x: (
                -x[0],
                x[1],
            )
        )

        _, _, winner_index, chosen = candidates[0]
        winner = self.players[winner_index]

        self.log(
            f"{winner.name} ポカ: {chosen.label()} "
            f"← {self.players[discarder_index].name}"
        )

        self.remove_role_cards_from_hand(
            winner,
            chosen,
            external_card=discarded_card,
        )

        self.pay_discard_role(
            winner_index,
            discarder_index,
            chosen.total_score,
        )

        self.resolve_replacement_draws(
            winner_index,
            len(chosen.cards) - 1,
        )

    # --------------------------------------------------------
    # 1ターン
    # --------------------------------------------------------

    def play_turn(self) -> None:
        if self.is_finished():
            return

        i = self.turn_index
        player = self.players[i]
        agent = self.agents[i]
        self.turn_count += 1

        self.log(
            f"\n=== Turn {self.turn_count}: {player.name} ==="
        )

        # 1. 山札から1枚引く
        drawn = self.draw_cards(player, 1)
        if drawn:
            self.log(f"draw: {drawn[0].short()}")

        if self.is_finished():
            return

        # 2. 自分の役を宣言
        self.resolve_self_draw_roles(i)

        if self.is_finished():
            return

        # 3. 1枚捨てる
        if not player.hand:
            return

        discarded = agent.choose_discard(self, i)
        player.hand.remove(discarded)
        self.discards.append(discarded)

        self.log(f"discard: {discarded.short()}")

        # 4. 他家のポカ判定
        self.resolve_discard_claims(i, discarded)

        if not self.is_finished():
            self.turn_index = (self.turn_index + 1) % 4

    # --------------------------------------------------------
    # 終了
    # --------------------------------------------------------

    def is_finished(self) -> bool:
        return (not self.deck) or any(p.coins <= 0 for p in self.players)

    def end_reason(self) -> str:
        if any(p.coins <= 0 for p in self.players):
            return "coin_zero"
        if not self.deck:
            return "deck_empty"
        return "ongoing"

    def result(self) -> GameResult:
        max_coin = max(p.coins for p in self.players)
        winners = [p.name for p in self.players if p.coins == max_coin]

        return GameResult(
            winner_names=winners,
            final_coins={p.name: p.coins for p in self.players},
            turns=self.turn_count,
            end_reason=self.end_reason(),
        )

    def run(self, max_turns: int = 10000) -> GameResult:
        while not self.is_finished():
            self.play_turn()

            if self.turn_count >= max_turns:
                raise RuntimeError("max_turnsに到達しました。無限ループの可能性があります。")

        return self.result()

    def summary(self) -> str:
        lines = [
            f"登場グループ: {', '.join(self.selected_groups)}",
            f"登場ホロメン: {len(self.active_members)}人",
            f"ボーナス: {self.bonus_member}",
            f"山札: {len(self.deck)}枚",
            f"ゲーム外カード: {len(self.unused_cards)}枚",
            f"ターン数: {self.turn_count}",
        ]
        for p in self.players:
            lines.append(
                f"{p.name}: {p.coins}点 / 手牌{len(p.hand)}枚"
            )
        return "\n".join(lines)


# ============================================================
# 一括シミュレーション
# ============================================================

def simulate_many(
    games: int = 1000,
    seed: int = 0,
    starting_coins: int = 1000,
) -> dict:
    master_rng = random.Random(seed)

    wins = Counter()
    end_reasons = Counter()
    total_turns = 0
    total_final_coins = Counter()

    for _ in range(games):
        game_seed = master_rng.randrange(10**18)

        game = PokaJanGame(
            seed=game_seed,
            starting_coins=starting_coins,
            verbose=False,
        )

        result = game.run()

        total_turns += result.turns
        end_reasons[result.end_reason] += 1

        # 同点1位は人数で割る
        share = 1 / len(result.winner_names)
        for w in result.winner_names:
            wins[w] += share

        for name, coins in result.final_coins.items():
            total_final_coins[name] += coins

    return {
        "games": games,
        "win_rates": {
            name: wins[name] / games
            for name in ("P1", "P2", "P3", "P4")
        },
        "average_final_coins": {
            name: total_final_coins[name] / games
            for name in ("P1", "P2", "P3", "P4")
        },
        "average_turns": total_turns / games,
        "end_reasons": dict(end_reasons),
    }


# ============================================================
# スモークテスト
# ============================================================

def smoke_test() -> None:
    game = PokaJanGame(seed=42, verbose=False)

    assert len(game.players) == 4
    assert all(len(p.hand) == 7 for p in game.players)
    assert len(game.deck) == 72
    assert len(game.selected_groups) == 4
    assert not (
        "JP1" in game.selected_groups and "GAMERS" in game.selected_groups
    )

    pool = make_full_card_pool(game.selected_groups)
    counts = Counter(c.member for c in pool)
    assert all(v == 9 for v in counts.values())

    result = game.run()

    assert game.is_finished()
    assert result.end_reason in {"deck_empty", "coin_zero"}

    print("=== 1ゲーム結果 ===")
    print(game.summary())
    print("winner:", result.winner_names)
    print("reason:", result.end_reason)

    print("\n=== 100ゲーム試走 ===")
    stats = simulate_many(games=100, seed=123)
    print(stats)




# ============================================================
# モンテカルロ打牌評価（v3追加）
# ============================================================

import copy
from dataclasses import dataclass as _dataclass


@_dataclass
class DiscardEvaluation:
    card: Card
    simulations: int
    win_rate: float
    average_final_coins: float
    average_rank: float
    bust_rate: float

    def as_dict(self) -> dict:
        return {
            "card": self.card.short(),
            "simulations": self.simulations,
            "win_rate": self.win_rate,
            "average_final_coins": self.average_final_coins,
            "average_rank": self.average_rank,
            "bust_rate": self.bust_rate,
        }


def _rank_of_player(players: list[Player], player_index: int) -> float:
    """
    同点順位は平均順位。
    例: 1位同点2人なら1.5位。
    """
    target = players[player_index].coins
    better = sum(p.coins > target for p in players)
    equal = sum(p.coins == target for p in players)
    return better + (equal + 1) / 2


def _clone_with_new_rng(game: PokaJanGame, seed: int) -> PokaJanGame:
    """
    現在局面を完全コピーし、以後のAI乱数だけ独立させる。
    山札順そのものはコピーされる。

    現段階では「シミュレーター内部だけが真の山札順を知っている」
    完全情報モード。後で実戦用に、未知カードを再サンプリングする
    不完全情報モードへ拡張する。
    """
    sim = copy.deepcopy(game)
    sim.rng = random.Random(seed)
    sim.verbose = False
    return sim


def _force_discard_and_continue(
    game: PokaJanGame,
    player_index: int,
    card: Card,
) -> GameResult:
    """
    現在が「自分の役処理を終えて、これから打牌する瞬間」
    であることを想定。
    指定カードを強制的に捨て、その後ゲーム終了までランダムAIで進行。
    """
    player = game.players[player_index]

    if card not in player.hand:
        raise ValueError("指定カードが手札にありません。")

    player.hand.remove(card)
    game.discards.append(card)

    game.resolve_discard_claims(player_index, card)

    if not game.is_finished():
        game.turn_index = (player_index + 1) % 4

    return game.run()


def evaluate_discards_monte_carlo(
    game: PokaJanGame,
    player_index: int,
    simulations_per_card: int = 500,
    seed: int = 2026,
) -> list[DiscardEvaluation]:
    """
    各打牌候補を同じ回数だけシミュレーションし、
    - 1位率
    - 平均最終コイン
    - 平均順位
    - コイン0率
    を比較する。

    同一ホロメン・同一色・異なるcopy_noはゲーム上同価値なので、
    評価候補を(member, color)単位にまとめる。
    """
    if simulations_per_card <= 0:
        raise ValueError("simulations_per_card は1以上にしてください。")

    player = game.players[player_index]
    if not player.hand:
        return []

    # ゲーム上同価値のカード個体をまとめる
    representative: dict[tuple[str, str], Card] = {}
    for c in player.hand:
        representative.setdefault((c.member, c.color), c)

    master_rng = random.Random(seed)
    evaluations: list[DiscardEvaluation] = []

    for _, card in representative.items():
        wins = 0.0
        final_coins_sum = 0.0
        rank_sum = 0.0
        busts = 0

        for _ in range(simulations_per_card):
            sim_seed = master_rng.randrange(10**18)
            sim = _clone_with_new_rng(game, sim_seed)

            # deepcopy後はCardが値比較可能なので元cardでremoveできる
            result = _force_discard_and_continue(
                sim,
                player_index,
                card,
            )

            target_name = sim.players[player_index].name
            if target_name in result.winner_names:
                wins += 1 / len(result.winner_names)

            final_coins = sim.players[player_index].coins
            final_coins_sum += final_coins
            rank_sum += _rank_of_player(sim.players, player_index)

            if final_coins <= 0:
                busts += 1

        n = simulations_per_card
        evaluations.append(
            DiscardEvaluation(
                card=card,
                simulations=n,
                win_rate=wins / n,
                average_final_coins=final_coins_sum / n,
                average_rank=rank_sum / n,
                bust_rate=busts / n,
            )
        )

    # デフォルトは1位率優先、次に平均順位、平均コイン
    evaluations.sort(
        key=lambda e: (
            e.win_rate,
            -e.average_rank,
            e.average_final_coins,
        ),
        reverse=True,
    )

    return evaluations


def prepare_random_discard_decision(
    seed: int = 7,
) -> tuple[PokaJanGame, int]:
    """
    デモ用:
    あるプレイヤーの「ドロー→自摸役処理」まで進め、
    これから捨てる直前の状態を返す。
    """
    game = PokaJanGame(seed=seed, verbose=False)
    i = game.turn_index
    player = game.players[i]

    game.draw_cards(player, 1)
    if not game.is_finished():
        game.resolve_self_draw_roles(i)

    return game, i


def monte_carlo_demo(
    simulations_per_card: int = 100,
    seed: int = 7,
) -> None:
    game, i = prepare_random_discard_decision(seed=seed)

    print("\n=== モンテカルロ打牌評価デモ ===")
    print("登場グループ:", game.selected_groups)
    print("ボーナス:", game.bonus_member)
    print("対象:", game.players[i].name)
    print("手札:")
    for c in game.players[i].hand:
        print(" ", c.short())

    evaluations = evaluate_discards_monte_carlo(
        game,
        i,
        simulations_per_card=simulations_per_card,
        seed=999,
    )

    print("\n推奨順位:")
    for rank, e in enumerate(evaluations, start=1):
        print(
            f"{rank:>2}. {e.card.short():<25} "
            f"1位率={e.win_rate:6.1%}  "
            f"平均順位={e.average_rank:.3f}  "
            f"平均最終点={e.average_final_coins:.1f}  "
            f"飛び率={e.bust_rate:5.1%}"
        )






# ============================================================
# ヒューリスティックAI（v4追加）
# ============================================================

class HeuristicAgent:
    """
    RandomAgent より賢い基準AI。

    評価方針:
    1. 成立している役は、基本的に高得点を優先
    2. 打牌時は、
       - 自分の役への近さ
       - 同色役への近さ
       - ボーナスホロメン
       - 相手にポカされる危険度
       をまとめて評価
    """

    def __init__(
        self,
        role_score_weight: float = 1.0,
        future_role_weight: float = 1.0,
        bonus_keep_weight: float = 35.0,
        danger_weight: float = 1.0,
    ):
        self.role_score_weight = role_score_weight
        self.future_role_weight = future_role_weight
        self.bonus_keep_weight = bonus_keep_weight
        self.danger_weight = danger_weight

    # --------------------------------------------------------
    # 役選択
    # --------------------------------------------------------

    def choose_self_draw_role(
        self,
        game: "PokaJanGame",
        player_index: int,
        roles: list[Role],
    ) -> Role | None:
        if not roles:
            return None

        player = game.players[player_index]

        best_role = None
        best_value = float("-inf")

        for role in roles:
            # いま取れる点
            immediate = role.total_score * self.role_score_weight

            # 役に使った後の手札価値
            remaining = list(player.hand)
            for c in role.cards:
                remaining.remove(c)

            future = self._hand_potential(
                game,
                remaining,
                player_index,
            ) * self.future_role_weight

            value = immediate + future

            if value > best_value:
                best_value = value
                best_role = role

        return best_role

    def choose_discard_claim(
        self,
        game: "PokaJanGame",
        player_index: int,
        roles: list[Role],
    ) -> Role | None:
        # 現状は、ポカできるなら基本的に最大価値の役を選ぶ
        if not roles:
            return None

        return max(
            roles,
            key=lambda r: (
                r.total_score,
                r.same_color,
                len(r.cards),
            )
        )

    # --------------------------------------------------------
    # 打牌
    # --------------------------------------------------------

    def choose_discard(
        self,
        game: "PokaJanGame",
        player_index: int,
    ) -> Card:
        player = game.players[player_index]

        # 同一member/colorはゲーム上ほぼ等価なので代表だけ評価
        representatives: dict[tuple[str, str], Card] = {}
        for card in player.hand:
            representatives.setdefault(
                (card.member, card.color),
                card
            )

        best_card = None
        best_value = float("-inf")

        for card in representatives.values():
            remaining = list(player.hand)
            remaining.remove(card)

            # 残した手札の将来価値
            own_value = self._hand_potential(
                game,
                remaining,
                player_index,
            )

            # 捨てた瞬間の相手への危険度
            danger = self._discard_danger(
                game,
                player_index,
                card,
            )

            # 捨てるカード自体がボーナスなら少しペナルティ
            bonus_penalty = (
                self.bonus_keep_weight
                if card.member == game.bonus_member
                else 0.0
            )

            value = (
                own_value
                - self.danger_weight * danger
                - bonus_penalty
            )

            # 同点ならランダムに散らして固定癖を避ける
            value += game.rng.random() * 1e-6

            if value > best_value:
                best_value = value
                best_card = card

        return best_card

    # --------------------------------------------------------
    # 自分の手札価値
    # --------------------------------------------------------

    def _hand_potential(
        self,
        game: "PokaJanGame",
        hand: list[Card],
        player_index: int,
    ) -> float:
        """
        手牌が将来どれくらい役に近いかをざっくり数値化する。

        完成役そのものより、
        「あと何種類 / 何枚で役になるか」を重視する。
        """
        value = 0.0

        # ------------------------------
        # A. 同じホロメン3枚
        # ------------------------------
        by_member: dict[str, list[Card]] = {}
        for c in hand:
            by_member.setdefault(c.member, []).append(c)

        for member, cards in by_member.items():
            n = len(cards)

            # 3枚以上持っている価値
            if n >= 3:
                value += 160.0
            elif n == 2:
                value += 90.0
            elif n == 1:
                value += 22.0

            # 同色3枚への近さ
            color_counts = Counter(c.color for c in cards)

            for count in color_counts.values():
                if count >= 3:
                    value += 320.0
                elif count == 2:
                    value += 145.0
                elif count == 1:
                    value += 18.0

            # 3色異色役への近さ
            distinct_colors = len(color_counts)
            if distinct_colors == 3:
                value += 110.0
            elif distinct_colors == 2:
                value += 55.0

            # ボーナスホロメンは保持価値を加算
            if member == game.bonus_member:
                value += self.bonus_keep_weight * n

        # ------------------------------
        # B. グループ役
        # ------------------------------
        for group in game.selected_groups:
            members = GROUPS[group]
            group_size = len(members)

            held_by_member: dict[str, list[Card]] = {
                m: [c for c in hand if c.member == m]
                for m in members
            }

            distinct_members = sum(
                bool(cards)
                for cards in held_by_member.values()
            )

            missing = group_size - distinct_members

            # 高人数グループほど完成点が高いので重みを増す
            size_weight = {
                3: 1.0,
                4: 1.45,
                5: 2.0,
            }[group_size]

            # 「あと1人」が特に重要
            if missing == 0:
                value += 180.0 * size_weight
            elif missing == 1:
                value += 115.0 * size_weight
            elif missing == 2:
                value += 48.0 * size_weight
            elif missing == 3:
                value += 16.0 * size_weight

            # 同色グループ役への近さ
            for color in COLORS:
                same_color_members = sum(
                    any(c.color == color for c in cards)
                    for cards in held_by_member.values()
                )

                color_missing = group_size - same_color_members

                if color_missing == 0:
                    value += 420.0 * size_weight
                elif color_missing == 1:
                    value += 210.0 * size_weight
                elif color_missing == 2:
                    value += 70.0 * size_weight

            # ボーナスメンバーをグループ役で使える場合
            if game.bonus_member in members:
                bonus_cards = sum(
                    c.member == game.bonus_member
                    for c in hand
                )
                value += 20.0 * bonus_cards

        return value

    # --------------------------------------------------------
    # 捨て牌危険度
    # --------------------------------------------------------

    def _discard_danger(
        self,
        game: "PokaJanGame",
        discarder_index: int,
        card: Card,
    ) -> float:
        """
        現段階ではシミュレーター内部で相手手札が見えているため、
        「実際にこの牌でポカされるか」を直接チェックする。

        実戦AIではここを不完全情報推定に置き換える。
        """
        danger = 0.0

        for i, opponent in enumerate(game.players):
            if i == discarder_index:
                continue

            roles = roles_completed_by_discard(
                opponent.hand,
                card,
                game.selected_groups,
                game.bonus_member,
            )

            if roles:
                # 相手が選べる最大得点を危険度とする
                max_score = max(r.total_score for r in roles)
                danger += max_score

        return danger


def make_heuristic_agents() -> list[HeuristicAgent]:
    return [HeuristicAgent() for _ in range(4)]


def compare_random_vs_heuristic(
    games: int = 200,
    seed: int = 1234,
    starting_coins: int = 1000,
) -> dict:
    """
    P1,P2 = HeuristicAgent
    P3,P4 = RandomAgent
    として比較する簡易テスト。
    """
    master_rng = random.Random(seed)

    wins = Counter()
    total_final = Counter()
    end_reasons = Counter()

    for _ in range(games):
        game = PokaJanGame(
            seed=master_rng.randrange(10**18),
            starting_coins=starting_coins,
            agents=[
                HeuristicAgent(),
                HeuristicAgent(),
                RandomAgent(),
                RandomAgent(),
            ],
            verbose=False,
        )

        result = game.run()
        end_reasons[result.end_reason] += 1

        share = 1 / len(result.winner_names)
        for w in result.winner_names:
            wins[w] += share

        for name, coins in result.final_coins.items():
            total_final[name] += coins

    return {
        "games": games,
        "win_rates": {
            name: wins[name] / games
            for name in ("P1", "P2", "P3", "P4")
        },
        "average_final_coins": {
            name: total_final[name] / games
            for name in ("P1", "P2", "P3", "P4")
        },
        "end_reasons": dict(end_reasons),
    }




# ============================================================
# 不完全情報ヒューリスティックAI（v5）
# ============================================================

class ImperfectInfoHeuristicAgent(HeuristicAgent):
    """
    相手の実手札を見ず、公開情報だけで危険度を推定するAI。

    公開情報:
    - 今回の4グループ
    - 自分の手札
    - 捨て札
    - 各プレイヤーの現在手札枚数
    - 山札残り枚数
    - 100枚だけ採用されるルール

    未知カードを複数回ランダム配置して、
    この打牌が相手のポカを完成させる確率と期待失点を推定する。
    """

    def __init__(
        self,
        role_score_weight: float = 1.0,
        future_role_weight: float = 1.0,
        bonus_keep_weight: float = 35.0,
        danger_weight: float = 1.0,
        danger_samples: int = 12,
    ):
        super().__init__(
            role_score_weight=role_score_weight,
            future_role_weight=future_role_weight,
            bonus_keep_weight=bonus_keep_weight,
            danger_weight=danger_weight,
        )
        self.danger_samples = danger_samples

    def _public_known_cards(
        self,
        game: "PokaJanGame",
        player_index: int,
    ) -> list[Card]:
        return (
            list(game.players[player_index].hand)
            + list(game.discards)
        )

    def _sample_hidden_hands(
        self,
        game: "PokaJanGame",
        player_index: int,
        rng: random.Random,
    ) -> dict[int, list[Card]]:
        """
        4グループの全候補から公開カードを除き、
        「現在ゲーム内に残っているはずの未知カード枚数」だけ採用。
        そこから相手3人の手札をランダムに割り当てる。

        残り候補の一部は、最初の100枚抽選で採用されなかったカード
        または既に役宣言でゲームから消えたカードとして扱われる。
        """
        pool = make_full_card_pool(game.selected_groups)

        for c in self._public_known_cards(game, player_index):
            pool.remove(c)

        opponent_indices = [
            i for i in range(4)
            if i != player_index
        ]

        opponent_card_count = sum(
            len(game.players[i].hand)
            for i in opponent_indices
        )

        hidden_in_play_count = min(
            opponent_card_count + len(game.deck),
            len(pool),
        )

        hidden_in_play = rng.sample(
            pool,
            hidden_in_play_count,
        )
        rng.shuffle(hidden_in_play)

        hands = {}
        cursor = 0

        for i in opponent_indices:
            n = len(game.players[i].hand)
            hands[i] = hidden_in_play[cursor:cursor+n]
            cursor += n

        return hands

    def estimate_discard_risk(
        self,
        game: "PokaJanGame",
        discarder_index: int,
        card: Card,
        samples: int | None = None,
    ) -> dict:
        samples = (
            self.danger_samples
            if samples is None
            else samples
        )

        if samples <= 0:
            return {
                "claim_probability": 0.0,
                "expected_loss": 0.0,
                "conditional_loss": 0.0,
                "max_loss": 0.0,
            }

        # Pythonのhashランダム化に依存しない簡単なseed
        seed_text = (
            f"{game.turn_count}|{discarder_index}|"
            f"{card.member}|{card.color}|"
            f"{len(game.deck)}|{len(game.discards)}"
        )
        local_seed = sum(
            (i + 1) * ord(ch)
            for i, ch in enumerate(seed_text)
        )
        rng = random.Random(local_seed)

        claim_worlds = 0
        total_loss = 0.0
        max_loss = 0.0

        for _ in range(samples):
            sampled_hands = self._sample_hidden_hands(
                game,
                discarder_index,
                rng,
            )

            # 複数人同時ポカの正式ルールは未確定なので、
            # 危険度推定では「その世界で最も高い1件」を採用。
            # これなら二重・三重請求を勝手に仮定しない。
            world_loss = 0.0

            for opponent_index, sampled_hand in sampled_hands.items():
                roles = roles_completed_by_discard(
                    sampled_hand,
                    card,
                    game.selected_groups,
                    game.bonus_member,
                )

                if roles:
                    world_loss = max(
                        world_loss,
                        max(r.total_score for r in roles),
                    )

            if world_loss > 0:
                claim_worlds += 1
                total_loss += world_loss
                max_loss = max(max_loss, world_loss)

        return {
            "claim_probability": claim_worlds / samples,
            "expected_loss": total_loss / samples,
            "conditional_loss": (
                total_loss / claim_worlds
                if claim_worlds
                else 0.0
            ),
            "max_loss": max_loss,
        }

    def _discard_danger(
        self,
        game: "PokaJanGame",
        discarder_index: int,
        card: Card,
    ) -> float:
        return self.estimate_discard_risk(
            game,
            discarder_index,
            card,
        )["expected_loss"]


def make_imperfect_agents(
    danger_samples: int = 12,
) -> list[ImperfectInfoHeuristicAgent]:
    return [
        ImperfectInfoHeuristicAgent(
            danger_samples=danger_samples
        )
        for _ in range(4)
    ]


def public_risk_table(
    game: "PokaJanGame",
    player_index: int,
    samples: int = 200,
) -> list[dict]:
    """
    分析用。通常対局より多めにサンプリングして、
    各打牌の危険度表を返す。
    """
    agent = ImperfectInfoHeuristicAgent(
        danger_samples=samples
    )

    player = game.players[player_index]

    reps = {}
    for c in player.hand:
        reps.setdefault((c.member, c.color), c)

    rows = []

    for c in reps.values():
        risk = agent.estimate_discard_risk(
            game,
            player_index,
            c,
            samples=samples,
        )
        rows.append({
            "card": c.short(),
            **risk,
        })

    rows.sort(
        key=lambda row: (
            row["expected_loss"],
            row["claim_probability"],
        )
    )
    return rows


def quick_imperfect_demo(
    seed: int = 17,
    samples: int = 100,
) -> None:
    game = PokaJanGame(
        seed=seed,
        agents=make_imperfect_agents(
            danger_samples=8
        ),
        verbose=False,
    )

    i = game.turn_index
    player = game.players[i]

    # 打牌直前まで
    game.draw_cards(player, 1)
    if not game.is_finished():
        game.resolve_self_draw_roles(i)

    print("=== 不完全情報AI 危険度デモ ===")
    print("登場グループ:", game.selected_groups)
    print("ボーナス:", game.bonus_member)

    for row in public_risk_table(
        game,
        i,
        samples=samples,
    ):
        print(
            f"{row['card']:<30} "
            f"ポカ率={row['claim_probability']:6.1%} "
            f"期待失点={row['expected_loss']:7.1f} "
            f"被ポカ時平均={row['conditional_loss']:7.1f}"
        )

    # 軽量設定で1ゲーム完走できることを確認
    result = game.run()
    print("終了:", result.end_reason)
    print("最終点:", result.final_coins)



# ============================================================
# 実戦用：現在手札の打牌ランキング（v6）
# ============================================================

def analyze_discard_choices(
    game: "PokaJanGame",
    player_index: int,
    risk_samples: int = 300,
) -> list[dict]:
    """
    打牌直前の手札について各候補を評価。
    相手の実手札は使わず、公開情報から危険度を推定する。

    score は大きいほど推奨。
    内訳:
      remaining_potential = その牌を切った後の手牌価値
      expected_loss       = 被ポカ期待失点
      bonus_penalty       = ボーナス牌を手放すペナルティ
    """
    player = game.players[player_index]
    evaluator = ImperfectInfoHeuristicAgent(
        danger_samples=risk_samples
    )

    reps = {}
    for c in player.hand:
        reps.setdefault((c.member, c.color), c)

    rows = []
    for card in reps.values():
        remaining = list(player.hand)
        remaining.remove(card)

        potential = evaluator._hand_potential(
            game, remaining, player_index
        )
        risk = evaluator.estimate_discard_risk(
            game, player_index, card, samples=risk_samples
        )
        bonus_penalty = (
            evaluator.bonus_keep_weight
            if card.member == game.bonus_member
            else 0.0
        )
        score = (
            potential
            - evaluator.danger_weight * risk["expected_loss"]
            - bonus_penalty
        )

        rows.append({
            "card": card,
            "score": score,
            "remaining_potential": potential,
            "claim_probability": risk["claim_probability"],
            "expected_loss": risk["expected_loss"],
            "conditional_loss": risk["conditional_loss"],
            "bonus_discard": card.member == game.bonus_member,
        })

    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows


def print_discard_analysis(
    game: "PokaJanGame",
    player_index: int,
    risk_samples: int = 300,
) -> None:
    player = game.players[player_index]
    rows = analyze_discard_choices(
        game, player_index, risk_samples=risk_samples
    )

    print("\n=== 打牌ランキング ===")
    print("登場グループ:", game.selected_groups)
    print("ボーナス:", game.bonus_member)
    print("持ち点:", {p.name: p.coins for p in game.players})
    print("対象:", player.name)
    print("手札:", " / ".join(c.short() for c in player.hand))

    for n, row in enumerate(rows, 1):
        bonus = " BONUS" if row["bonus_discard"] else ""
        print(
            f"{n:>2}. {row['card'].short():<30}"
            f" 評価={row['score']:8.1f}"
            f" 手牌価値={row['remaining_potential']:8.1f}"
            f" ポカ率={row['claim_probability']:6.1%}"
            f" 期待失点={row['expected_loss']:7.1f}"
            f"{bonus}"
        )


def decision_demo(seed: int = 17, risk_samples: int = 150) -> None:
    game = PokaJanGame(
        seed=seed,
        starting_coins=1000,
        agents=make_imperfect_agents(danger_samples=10),
        verbose=False,
    )
    i = game.turn_index
    player = game.players[i]

    # 自分の番：1枚引く→成立役を処理→打牌直前
    game.draw_cards(player, 1)
    if not game.is_finished():
        game.resolve_self_draw_roles(i)

    print_discard_analysis(
        game, i, risk_samples=risk_samples
    )




# ============================================================
# コイン期待値ベース打牌評価（v7）
# ============================================================

@dataclass
class CoinDiscardEvaluation:
    card: Card
    simulations: int
    average_final_coins: float
    expected_coin_change: float
    median_final_coins: float
    bust_rate: float

    def as_dict(self) -> dict:
        return {
            "card": self.card.short(),
            "simulations": self.simulations,
            "average_final_coins": self.average_final_coins,
            "expected_coin_change": self.expected_coin_change,
            "median_final_coins": self.median_final_coins,
            "bust_rate": self.bust_rate,
        }


def evaluate_discards_by_coins(
    game: PokaJanGame,
    player_index: int,
    simulations_per_card: int = 300,
    seed: int = 2026,
) -> list[CoinDiscardEvaluation]:
    """
    各打牌を、その後の最終コインだけで評価する。

    主指標:
      average_final_coins
        = その打牌後にゲーム終了まで進めたときの平均最終コイン

    補助指標:
      expected_coin_change
        = 現在コインから平均で何コイン増減するか
      median_final_coins
        = 外れ値に左右されにくい中央値
      bust_rate
        = 0コインになる割合

    順位・1位率は一切評価に使わない。
    """
    if simulations_per_card <= 0:
        raise ValueError("simulations_per_card は1以上にしてください。")

    player = game.players[player_index]
    starting_coins = player.coins

    # 同一ホロメン・同色・異なるcopy_noは同価値なので代表だけ評価
    representatives: dict[tuple[str, str], Card] = {}
    for c in player.hand:
        representatives.setdefault((c.member, c.color), c)

    master_rng = random.Random(seed)
    evaluations: list[CoinDiscardEvaluation] = []

    for card in representatives.values():
        finals = []
        busts = 0

        for _ in range(simulations_per_card):
            sim_seed = master_rng.randrange(10**18)
            sim = _clone_with_new_rng(game, sim_seed)

            _force_discard_and_continue(
                sim,
                player_index,
                card,
            )

            final_coins = sim.players[player_index].coins
            finals.append(final_coins)

            if final_coins <= 0:
                busts += 1

        finals_sorted = sorted(finals)
        n = len(finals_sorted)

        if n % 2 == 1:
            median = finals_sorted[n // 2]
        else:
            median = (
                finals_sorted[n // 2 - 1]
                + finals_sorted[n // 2]
            ) / 2

        avg = sum(finals_sorted) / n

        evaluations.append(
            CoinDiscardEvaluation(
                card=card,
                simulations=n,
                average_final_coins=avg,
                expected_coin_change=avg - starting_coins,
                median_final_coins=median,
                bust_rate=busts / n,
            )
        )

    # 最終コイン期待値を最優先。
    # 同値なら中央値、その次に飛び率の低さ。
    evaluations.sort(
        key=lambda e: (
            e.average_final_coins,
            e.median_final_coins,
            -e.bust_rate,
        ),
        reverse=True,
    )

    return evaluations


def print_coin_monte_carlo_analysis(
    game: PokaJanGame,
    player_index: int,
    simulations_per_card: int = 300,
    seed: int = 2026,
) -> None:
    player = game.players[player_index]

    rows = evaluate_discards_by_coins(
        game,
        player_index,
        simulations_per_card=simulations_per_card,
        seed=seed,
    )

    print("\n=== コイン期待値ベース打牌評価 ===")
    print("登場グループ:", game.selected_groups)
    print("ボーナス:", game.bonus_member)
    print("現在コイン:", player.coins)
    print("手札:", " / ".join(c.short() for c in player.hand))

    for rank, row in enumerate(rows, 1):
        sign = "+" if row.expected_coin_change >= 0 else ""
        print(
            f"{rank:>2}. {row.card.short():<30}"
            f" 平均最終={row.average_final_coins:7.1f}"
            f" 期待増減={sign}{row.expected_coin_change:7.1f}"
            f" 中央値={row.median_final_coins:7.1f}"
            f" 0点率={row.bust_rate:6.1%}"
        )


def coin_decision_demo(
    seed: int = 17,
    simulations_per_card: int = 80,
) -> None:
    """
    実戦に近いデモ:
    1000コインスタートで打牌直前局面を作り、
    各打牌を最終コイン期待値で比較する。
    """
    game = PokaJanGame(
        seed=seed,
        starting_coins=1000,
        agents=make_imperfect_agents(danger_samples=8),
        verbose=False,
    )

    i = game.turn_index
    player = game.players[i]

    game.draw_cards(player, 1)

    if not game.is_finished():
        game.resolve_self_draw_roles(i)

    print_coin_monte_carlo_analysis(
        game,
        i,
        simulations_per_card=simulations_per_card,
        seed=999,
    )



# ============================================================
# 不完全情報モンテカルロ打牌評価（v9）
# ============================================================

def _make_determinized_game(
    game: PokaJanGame,
    observer_index: int,
    seed: int,
    rollout_danger_samples: int = 4,
) -> PokaJanGame:
    """
    observer から見えない情報を1つの「あり得る世界」として再構成する。

    固定する公開情報:
      - 選択された4グループ
      - ボーナスホロメン
      - 各プレイヤーの現在コイン
      - observer自身の手札
      - 捨て札
      - 各プレイヤーの現在手札枚数
      - 現在の山札枚数
      - 現在の手番/ターン数

    再サンプリングする非公開情報:
      - 相手3人の具体的な手札
      - 残り山札の中身と順番

    100枚抽選で採用されなかったカードや、
    既に役宣言で除去されたカードは、
    「現在ゲーム内に必要な枚数」に採用されなかった残りとして扱う。
    """
    rng = random.Random(seed)

    # システム構造をコピーした後、非公開領域だけ差し替える
    sim = copy.deepcopy(game)
    sim.rng = random.Random(seed)
    sim.verbose = False

    # rollout中は全員、不完全情報ヒューリスティックAIを使用
    sim.agents = [
        ImperfectInfoHeuristicAgent(
            danger_samples=rollout_danger_samples
        )
        for _ in range(4)
    ]

    # 全候補カードを生成
    pool = make_full_card_pool(game.selected_groups)

    # observerから確実に見えているカードを除く
    visible_cards = (
        list(game.players[observer_index].hand)
        + list(game.discards)
    )

    for card in visible_cards:
        pool.remove(card)

    opponent_indices = [
        i for i in range(4)
        if i != observer_index
    ]

    opponent_hand_sizes = {
        i: len(game.players[i].hand)
        for i in opponent_indices
    }

    needed_hidden_cards = (
        sum(opponent_hand_sizes.values())
        + len(game.deck)
    )

    if needed_hidden_cards > len(pool):
        raise RuntimeError(
            "公開情報とカードプールの整合性が取れません。"
        )

    # 現時点でゲーム内に残っている未知カードだけ抽選。
    # 残り候補は「100枚に入らなかった/既に役で消えた」とみなす。
    hidden_in_play = rng.sample(
        pool,
        needed_hidden_cards,
    )
    rng.shuffle(hidden_in_play)

    cursor = 0

    # 相手手札を再構成
    for i in opponent_indices:
        n = opponent_hand_sizes[i]
        sim.players[i].hand = list(
            hidden_in_play[cursor:cursor+n]
        )
        cursor += n

    # 自分の手札は公開情報なのでそのまま
    sim.players[observer_index].hand = list(
        game.players[observer_index].hand
    )

    # 残りを山札にし、さらに順序も未知としてランダム化
    sampled_deck = list(hidden_in_play[cursor:])
    rng.shuffle(sampled_deck)
    sim.deck = sampled_deck

    # 捨て札・コイン・手番などは deepcopy の公開状態を維持
    return sim


def _force_discard_and_rollout(
    sim: PokaJanGame,
    player_index: int,
    card: Card,
) -> GameResult:
    """
    打牌直前局面から指定牌を強制的に切り、
    その後ゲーム終了まで進める。
    """
    player = sim.players[player_index]

    if card not in player.hand:
        raise ValueError(
            f"指定カード {card.short()} が手札にありません。"
        )

    player.hand.remove(card)
    sim.discards.append(card)

    # 捨て牌に対するポカ処理
    sim.resolve_discard_claims(
        player_index,
        card,
    )

    if not sim.is_finished():
        sim.turn_index = (
            player_index + 1
        ) % 4

    return sim.run()


@dataclass
class ImperfectMonteCarloEvaluation:
    card: Card
    simulations: int
    average_final_coins: float
    expected_coin_change: float
    median_final_coins: float
    zero_rate: float
    min_final_coins: int
    max_final_coins: int

    def as_dict(self) -> dict:
        return {
            "card": self.card.short(),
            "simulations": self.simulations,
            "average_final_coins": self.average_final_coins,
            "expected_coin_change": self.expected_coin_change,
            "median_final_coins": self.median_final_coins,
            "zero_rate": self.zero_rate,
            "min_final_coins": self.min_final_coins,
            "max_final_coins": self.max_final_coins,
        }


def evaluate_discards_imperfect_monte_carlo(
    game: PokaJanGame,
    player_index: int,
    simulations_per_card: int = 200,
    seed: int = 20260808,
    rollout_danger_samples: int = 4,
) -> list[ImperfectMonteCarloEvaluation]:
    """
    実戦向けの本命評価。

    各打牌候補ごとに毎回:
      1. 相手手札・山札を公開情報から再サンプリング
      2. 指定牌を切る
      3. 不完全情報AI4人でゲーム終了まで進行
      4. 自分の最終コインを記録

    順位や1位率は使わず、
    average_final_coins（平均最終コイン）が最大の牌を最善とする。
    """
    if simulations_per_card <= 0:
        raise ValueError(
            "simulations_per_card は1以上にしてください。"
        )

    player = game.players[player_index]
    current_coins = player.coins

    representatives: dict[tuple[str, str], Card] = {}
    for card in player.hand:
        representatives.setdefault(
            (card.member, card.color),
            card,
        )

    # 公平比較のため、全打牌候補に同じworld seed列を使う。
    master_rng = random.Random(seed)
    world_seeds = [
        master_rng.randrange(10**18)
        for _ in range(simulations_per_card)
    ]

    evaluations = []

    for card in representatives.values():
        finals = []

        for world_seed in world_seeds:
            sim = _make_determinized_game(
                game,
                observer_index=player_index,
                seed=world_seed,
                rollout_danger_samples=rollout_danger_samples,
            )

            _force_discard_and_rollout(
                sim,
                player_index,
                card,
            )

            finals.append(
                sim.players[player_index].coins
            )

        ordered = sorted(finals)
        n = len(ordered)

        if n % 2:
            median = ordered[n // 2]
        else:
            median = (
                ordered[n // 2 - 1]
                + ordered[n // 2]
            ) / 2

        avg = sum(ordered) / n

        evaluations.append(
            ImperfectMonteCarloEvaluation(
                card=card,
                simulations=n,
                average_final_coins=avg,
                expected_coin_change=(
                    avg - current_coins
                ),
                median_final_coins=median,
                zero_rate=sum(
                    x == 0 for x in ordered
                ) / n,
                min_final_coins=min(ordered),
                max_final_coins=max(ordered),
            )
        )

    # 最重要指標は平均最終コインのみ。
    # 完全同値の場合だけ中央値・0点率をタイブレークに使う。
    evaluations.sort(
        key=lambda e: (
            e.average_final_coins,
            e.median_final_coins,
            -e.zero_rate,
        ),
        reverse=True,
    )

    return evaluations


def print_imperfect_monte_carlo_analysis(
    game: PokaJanGame,
    player_index: int,
    simulations_per_card: int = 200,
    seed: int = 20260808,
    rollout_danger_samples: int = 4,
) -> None:
    rows = evaluate_discards_imperfect_monte_carlo(
        game,
        player_index,
        simulations_per_card=simulations_per_card,
        seed=seed,
        rollout_danger_samples=rollout_danger_samples,
    )

    player = game.players[player_index]

    print("\n=== 不完全情報モンテカルロ打牌評価 ===")
    print("登場グループ:", game.selected_groups)
    print("ボーナス:", game.bonus_member)
    print(
        "現在コイン:",
        {p.name: p.coins for p in game.players}
    )
    print(
        "対象手札:",
        " / ".join(c.short() for c in player.hand)
    )
    print(
        f"各打牌 {simulations_per_card} world"
    )

    for rank, row in enumerate(rows, 1):
        sign = (
            "+"
            if row.expected_coin_change >= 0
            else ""
        )

        print(
            f"{rank:>2}. {row.card.short():<30}"
            f" 平均最終={row.average_final_coins:7.1f}"
            f" 期待増減={sign}{row.expected_coin_change:7.1f}"
            f" 中央値={row.median_final_coins:7.1f}"
            f" 0点率={row.zero_rate:6.1%}"
            f" 範囲={row.min_final_coins}～{row.max_final_coins}"
        )


def imperfect_mc_demo(
    seed: int = 17,
    simulations_per_card: int = 20,
) -> None:
    """
    動作確認用。
    """
    game = PokaJanGame(
        seed=seed,
        starting_coins=1000,
        agents=make_imperfect_agents(
            danger_samples=4
        ),
        verbose=False,
    )

    i = game.turn_index
    player = game.players[i]

    # 打牌直前まで進める
    game.draw_cards(player, 1)

    if not game.is_finished():
        game.resolve_self_draw_roles(i)

    print_imperfect_monte_carlo_analysis(
        game,
        i,
        simulations_per_card=simulations_per_card,
        seed=999,
        rollout_danger_samples=3,
    )



# ============================================================
# 高速化版 不完全情報モンテカルロ（v13）
# ============================================================

class DeterminizedRolloutAgent(HeuristicAgent):
    """
    外側で一度「あり得る相手手札・山札」を確定した世界の中で使う高速AI。

    重要:
    - ルート局面の未知情報は _make_determinized_game_fast() で毎回再サンプリングする。
    - その確定世界の中では、さらに内側のモンテカルロを回さない。
    - これにより v12 の「モンテカルロの中でモンテカルロ」を解消する。

    ロールアウト専用なので、実戦時の推奨打牌そのものを
    このAIだけで決めるわけではない。
    """

    def _discard_danger(
        self,
        game: "PokaJanGame",
        discarder_index: int,
        card: Card,
    ) -> float:
        danger = 0.0

        # 確定済み世界の相手手札を直接使う。
        for i, opponent in enumerate(game.players):
            if i == discarder_index:
                continue

            roles = roles_completed_by_discard(
                opponent.hand,
                card,
                game.selected_groups,
                game.bonus_member,
            )

            if roles:
                # 実際のコインルールでは、相手の所持コインに関係なく
                # 上がり側は役の満額を受け取るため、役点そのものを危険度にする。
                danger += max(
                    r.total_score
                    for r in roles
                )

        return danger


_FULL_POOL_CACHE: dict[tuple[str, ...], tuple[Card, ...]] = {}


def _cached_full_card_pool(
    selected_groups: tuple[str, ...],
) -> list[Card]:
    """
    同じ4グループ構成の全カード生成を何千回も繰り返さないためのキャッシュ。
    呼び出し側で変更できるよう list コピーを返す。
    """
    key = tuple(selected_groups)

    if key not in _FULL_POOL_CACHE:
        _FULL_POOL_CACHE[key] = tuple(
            make_full_card_pool(key)
        )

    return list(_FULL_POOL_CACHE[key])


def _make_determinized_game_fast(
    game: PokaJanGame,
    observer_index: int,
    seed: int,
) -> PokaJanGame:
    """
    v9/v12 の determinization と同じ考え方だが、
    ロールアウトAIを DeterminizedRolloutAgent にして高速化。
    """
    rng = random.Random(seed)

    sim = copy.deepcopy(game)
    sim.rng = random.Random(seed)
    sim.verbose = False

    sim.agents = [
        DeterminizedRolloutAgent()
        for _ in range(4)
    ]

    pool = _cached_full_card_pool(
        tuple(game.selected_groups)
    )

    # observerから見えているカードだけ除く
    visible_cards = (
        list(game.players[observer_index].hand)
        + list(game.discards)
    )

    for card in visible_cards:
        pool.remove(card)

    opponent_indices = [
        i for i in range(4)
        if i != observer_index
    ]

    opponent_hand_sizes = {
        i: len(game.players[i].hand)
        for i in opponent_indices
    }

    needed_hidden_cards = (
        sum(opponent_hand_sizes.values())
        + len(game.deck)
    )

    if needed_hidden_cards > len(pool):
        raise RuntimeError(
            "公開情報とカードプールの整合性が取れません。"
        )

    hidden_in_play = rng.sample(
        pool,
        needed_hidden_cards,
    )
    rng.shuffle(hidden_in_play)

    cursor = 0

    for i in opponent_indices:
        n = opponent_hand_sizes[i]
        sim.players[i].hand = list(
            hidden_in_play[cursor:cursor+n]
        )
        cursor += n

    sim.players[observer_index].hand = list(
        game.players[observer_index].hand
    )

    sampled_deck = list(
        hidden_in_play[cursor:]
    )
    rng.shuffle(sampled_deck)
    sim.deck = sampled_deck

    return sim


def evaluate_discards_fast_monte_carlo(
    game: PokaJanGame,
    player_index: int,
    simulations_per_card: int = 100,
    seed: int = 20260808,
) -> list[ImperfectMonteCarloEvaluation]:
    """
    v13の推奨評価関数。

    各打牌:
      1. 公開情報から未知世界を再構成
      2. その牌を強制打牌
      3. 高速HeuristicAgentでゲーム終了までロールアウト
      4. 最終コインを記録

    評価基準は平均最終コインのみ。
    """
    if simulations_per_card <= 0:
        raise ValueError(
            "simulations_per_card は1以上にしてください。"
        )

    player = game.players[player_index]
    current_coins = player.coins

    representatives: dict[tuple[str, str], Card] = {}
    for card in player.hand:
        representatives.setdefault(
            (card.member, card.color),
            card,
        )

    # 全打牌で同じworld seedを使い、公平に比較
    master_rng = random.Random(seed)
    world_seeds = [
        master_rng.randrange(10**18)
        for _ in range(simulations_per_card)
    ]

    evaluations = []

    for card in representatives.values():
        finals = []

        for world_seed in world_seeds:
            sim = _make_determinized_game_fast(
                game,
                observer_index=player_index,
                seed=world_seed,
            )

            _force_discard_and_rollout(
                sim,
                player_index,
                card,
            )

            finals.append(
                sim.players[player_index].coins
            )

        ordered = sorted(finals)
        n = len(ordered)

        if n % 2:
            median = ordered[n // 2]
        else:
            median = (
                ordered[n // 2 - 1]
                + ordered[n // 2]
            ) / 2

        avg = sum(ordered) / n

        evaluations.append(
            ImperfectMonteCarloEvaluation(
                card=card,
                simulations=n,
                average_final_coins=avg,
                expected_coin_change=avg-current_coins,
                median_final_coins=median,
                zero_rate=sum(x == 0 for x in ordered)/n,
                min_final_coins=min(ordered),
                max_final_coins=max(ordered),
            )
        )

    evaluations.sort(
        key=lambda e: (
            e.average_final_coins,
            e.median_final_coins,
            -e.zero_rate,
        ),
        reverse=True,
    )

    return evaluations


def print_fast_monte_carlo_analysis(
    game: PokaJanGame,
    player_index: int,
    simulations_per_card: int = 100,
    seed: int = 20260808,
) -> None:
    rows = evaluate_discards_fast_monte_carlo(
        game,
        player_index,
        simulations_per_card=simulations_per_card,
        seed=seed,
    )

    player = game.players[player_index]

    print("\n=== v13 高速・不完全情報モンテカルロ ===")
    print("登場グループ:", game.selected_groups)
    print("ボーナス:", game.bonus_member)
    print(
        "現在コイン:",
        {p.name: p.coins for p in game.players}
    )
    print(
        "対象手札:",
        " / ".join(c.short() for c in player.hand)
    )
    print(
        f"各打牌 {simulations_per_card} world"
    )

    for rank, row in enumerate(rows, 1):
        sign = "+" if row.expected_coin_change >= 0 else ""

        print(
            f"{rank:>2}. {row.card.short():<30}"
            f" 平均最終={row.average_final_coins:7.1f}"
            f" 期待増減={sign}{row.expected_coin_change:7.1f}"
            f" 中央値={row.median_final_coins:7.1f}"
            f" 0点率={row.zero_rate:6.1%}"
        )


def fast_mc_demo(
    seed: int = 17,
    simulations_per_card: int = 20,
) -> None:
    game = PokaJanGame(
        seed=seed,
        starting_coins=1000,
        # ルート局面生成用。実際のrolloutでは高速AIに差し替わる。
        agents=make_imperfect_agents(
            danger_samples=2
        ),
        verbose=False,
    )

    i = game.turn_index
    player = game.players[i]

    game.draw_cards(player, 1)

    if not game.is_finished():
        game.resolve_self_draw_roles(i)

    print_fast_monte_carlo_analysis(
        game,
        i,
        simulations_per_card=simulations_per_card,
        seed=999,
    )



# ============================================================
# 収束チェック（v14）
# ============================================================

def convergence_analysis(
    game: PokaJanGame,
    player_index: int,
    sample_sizes: tuple[int, ...] = (20, 50, 100, 300),
    seed: int = 999,
) -> dict[int, list[ImperfectMonteCarloEvaluation]]:
    """
    同じ局面・同じ乱数系列の先頭部分を使い、
    試行回数を増やしたときに各打牌の平均最終コインが
    どのように安定していくかを見る。

    例:
      20 world
      50 world
      100 world
      300 world

    を比較できる。
    """
    results = {}

    for n in sample_sizes:
        rows = evaluate_discards_fast_monte_carlo(
            game,
            player_index,
            simulations_per_card=n,
            seed=seed,
        )
        results[n] = rows

    return results


def print_convergence_analysis(
    game: PokaJanGame,
    player_index: int,
    sample_sizes: tuple[int, ...] = (20, 50, 100, 300),
    seed: int = 999,
) -> None:
    """
    打牌ごとの期待値が試行回数とともにどう変化するかを表形式で表示。
    """
    results = convergence_analysis(
        game,
        player_index,
        sample_sizes=sample_sizes,
        seed=seed,
    )

    # 全候補カードを最初のsample sizeの手札順で確定
    first_n = sample_sizes[0]
    cards = [row.card for row in results[first_n]]

    # card表示名 -> 各nでの評価
    by_n = {
        n: {
            (row.card.member, row.card.color): row
            for row in rows
        }
        for n, rows in results.items()
    }

    print("\n=== v14 期待値収束チェック ===")
    print("登場グループ:", game.selected_groups)
    print("ボーナス:", game.bonus_member)
    print(
        "現在コイン:",
        {p.name: p.coins for p in game.players}
    )
    print(
        "対象手札:",
        " / ".join(
            c.short()
            for c in game.players[player_index].hand
        )
    )

    # ヘッダ
    header = f"{'打牌':<30}"
    for n in sample_sizes:
        header += f" {n:>8}w"
    print(header)
    print("-" * len(header))

    # カード順は最大sample size時の期待値順に並べる
    max_n = sample_sizes[-1]
    final_order = [
        (row.card.member, row.card.color)
        for row in results[max_n]
    ]

    for key in final_order:
        sample_row = by_n[first_n][key]
        line = f"{sample_row.card.short():<30}"

        for n in sample_sizes:
            row = by_n[n][key]
            line += f" {row.average_final_coins:8.1f}"

        print(line)

    print("\n最大試行回数での順位:")
    for rank, row in enumerate(results[max_n], 1):
        sign = "+" if row.expected_coin_change >= 0 else ""
        print(
            f"{rank:>2}. {row.card.short():<30}"
            f" 平均最終={row.average_final_coins:7.1f}"
            f" 期待増減={sign}{row.expected_coin_change:7.1f}"
            f" 0点率={row.zero_rate:6.1%}"
        )


def convergence_demo(
    seed: int = 17,
    sample_sizes: tuple[int, ...] = (20, 50, 100),
) -> None:
    """
    まずは軽めの20/50/100 worldで確認するデモ。
    """
    game = PokaJanGame(
        seed=seed,
        starting_coins=1000,
        agents=make_imperfect_agents(
            danger_samples=2
        ),
        verbose=False,
    )

    i = game.turn_index
    player = game.players[i]

    game.draw_cards(player, 1)

    if not game.is_finished():
        game.resolve_self_draw_roles(i)

    print_convergence_analysis(
        game,
        i,
        sample_sizes=sample_sizes,
        seed=999,
    )



# ============================================================
# 捨て牌履歴を使った相手手札推定（v15）
# ============================================================

def _discard_history_by_player(
    game: PokaJanGame,
) -> dict[int, list[Card]]:
    """
    現状のgame.discardsは捨て牌だけで誰が切ったかを持っていないため、
    v15では新たに player_discards を使う。

    既存ゲームとの互換性のため、属性がなければ空履歴を返す。
    """
    if hasattr(game, "player_discards"):
        return {
            i: list(game.player_discards.get(i, []))
            for i in range(4)
        }

    return {i: [] for i in range(4)}


def _card_group_memberships(
    game: PokaJanGame,
    member: str,
) -> set[str]:
    return {
        group
        for group in game.selected_groups
        if member in GROUPS[group]
    }


def _discard_based_weight(
    game: PokaJanGame,
    opponent_index: int,
    card: Card,
) -> float:
    """
    相手の過去の捨て牌から、そのカードを現在持っている尤度をざっくり調整。

    基本思想:
    - 同じホロメンを過去に何枚も切っている
      → そのホロメンを強く集めている可能性はやや低い
    - 同じグループのメンバーを多く切っている
      → そのグループ役を狙っている可能性はやや低い
    - 同じ色を多く切っている
      → その色の同色役を狙っている可能性を少し下げる

    これは確率モデルではなく、サンプリング重み用のヒューリスティック。
    """
    history = _discard_history_by_player(game)[opponent_index]

    if not history:
        return 1.0

    weight = 1.0

    # 同ホロメンの切り枚数
    same_member_count = sum(
        d.member == card.member
        for d in history
    )

    # 同色の切り枚数
    same_color_count = sum(
        d.color == card.color
        for d in history
    )

    # 同じ所属グループのカードをどれくらい切っているか
    card_groups = _card_group_memberships(
        game,
        card.member,
    )

    same_group_count = 0

    for d in history:
        d_groups = _card_group_memberships(
            game,
            d.member,
        )
        if card_groups & d_groups:
            same_group_count += 1

    # 切っているほど重みを下げる。
    # 下限は0.10にして、完全に「持っていない」とは決めつけない。
    weight *= 0.72 ** same_member_count
    weight *= 0.93 ** same_group_count
    weight *= 0.97 ** same_color_count

    return max(weight, 0.10)


def _weighted_sample_without_replacement(
    population: list[Card],
    weights: list[float],
    k: int,
    rng: random.Random,
) -> list[Card]:
    """
    重み付き・非復元抽出。
    Python標準random.choicesは復元抽出なので、
    1枚ずつ選んで除去する。
    """
    if k > len(population):
        raise ValueError("kがpopulationより大きいです。")

    pool = list(population)
    w = list(weights)
    selected = []

    for _ in range(k):
        total = sum(w)

        if total <= 0:
            idx = rng.randrange(len(pool))
        else:
            r = rng.random() * total
            acc = 0.0
            idx = len(pool) - 1

            for j, weight in enumerate(w):
                acc += weight
                if r <= acc:
                    idx = j
                    break

        selected.append(pool.pop(idx))
        w.pop(idx)

    return selected


def _assign_hidden_hands_with_discard_bias(
    game: PokaJanGame,
    observer_index: int,
    pool: list[Card],
    opponent_indices: list[int],
    rng: random.Random,
) -> tuple[dict[int, list[Card]], list[Card]]:
    """
    相手ごとに捨て牌履歴を反映した重み付きサンプリングで手札を割り当てる。
    残りを山札候補とする。
    """
    remaining = list(pool)
    sampled_hands = {}

    for opponent_index in opponent_indices:
        n = len(game.players[opponent_index].hand)

        weights = [
            _discard_based_weight(
                game,
                opponent_index,
                card,
            )
            for card in remaining
        ]

        hand = _weighted_sample_without_replacement(
            remaining,
            weights,
            n,
            rng,
        )

        sampled_hands[opponent_index] = hand

        # 選ばれたカードをremainingから除く
        for card in hand:
            remaining.remove(card)

    return sampled_hands, remaining


def _make_determinized_game_with_history(
    game: PokaJanGame,
    observer_index: int,
    seed: int,
) -> PokaJanGame:
    """
    v15版 determinization。

    相手手札:
      捨て牌履歴を反映して重み付きサンプリング

    山札:
      相手手札を割り当てた残り候補から必要枚数をランダム抽出

    ロールアウトAI:
      高速DeterminiziedRolloutAgent
    """
    rng = random.Random(seed)

    sim = copy.deepcopy(game)
    sim.rng = random.Random(seed)
    sim.verbose = False

    sim.agents = [
        DeterminizedRolloutAgent()
        for _ in range(4)
    ]

    pool = _cached_full_card_pool(
        tuple(game.selected_groups)
    )

    visible_cards = (
        list(game.players[observer_index].hand)
        + list(game.discards)
    )

    for card in visible_cards:
        pool.remove(card)

    opponent_indices = [
        i for i in range(4)
        if i != observer_index
    ]

    opponent_card_count = sum(
        len(game.players[i].hand)
        for i in opponent_indices
    )

    total_hidden_needed = (
        opponent_card_count
        + len(game.deck)
    )

    if total_hidden_needed > len(pool):
        raise RuntimeError(
            "公開情報とカードプールの整合性が取れません。"
        )

    # まず「現在ゲーム内に残っている未知カード」だけを抽出
    hidden_in_play = rng.sample(
        pool,
        total_hidden_needed,
    )

    # その中から相手手札を履歴バイアス付きで配る
    sampled_hands, remaining_hidden = (
        _assign_hidden_hands_with_discard_bias(
            game,
            observer_index,
            hidden_in_play,
            opponent_indices,
            rng,
        )
    )

    for i in opponent_indices:
        sim.players[i].hand = list(
            sampled_hands[i]
        )

    sim.players[observer_index].hand = list(
        game.players[observer_index].hand
    )

    # 残りが山札。順序は未知なのでシャッフル。
    sampled_deck = list(remaining_hidden)
    rng.shuffle(sampled_deck)
    sim.deck = sampled_deck

    return sim


def evaluate_discards_history_monte_carlo(
    game: PokaJanGame,
    player_index: int,
    simulations_per_card: int = 100,
    seed: int = 20260808,
) -> list[ImperfectMonteCarloEvaluation]:
    """
    捨て牌履歴を反映した不完全情報モンテカルロ。
    評価基準は最終コイン期待値。
    """
    player = game.players[player_index]
    current_coins = player.coins

    reps = {}
    for card in player.hand:
        reps.setdefault(
            (card.member, card.color),
            card,
        )

    master_rng = random.Random(seed)

    world_seeds = [
        master_rng.randrange(10**18)
        for _ in range(simulations_per_card)
    ]

    evaluations = []

    for card in reps.values():
        finals = []

        for world_seed in world_seeds:
            sim = _make_determinized_game_with_history(
                game,
                observer_index=player_index,
                seed=world_seed,
            )

            _force_discard_and_rollout(
                sim,
                player_index,
                card,
            )

            finals.append(
                sim.players[player_index].coins
            )

        ordered = sorted(finals)
        n = len(ordered)

        if n % 2:
            median = ordered[n // 2]
        else:
            median = (
                ordered[n // 2 - 1]
                + ordered[n // 2]
            ) / 2

        avg = sum(ordered) / n

        evaluations.append(
            ImperfectMonteCarloEvaluation(
                card=card,
                simulations=n,
                average_final_coins=avg,
                expected_coin_change=avg-current_coins,
                median_final_coins=median,
                zero_rate=sum(x == 0 for x in ordered)/n,
                min_final_coins=min(ordered),
                max_final_coins=max(ordered),
            )
        )

    evaluations.sort(
        key=lambda e: (
            e.average_final_coins,
            e.median_final_coins,
            -e.zero_rate,
        ),
        reverse=True,
    )

    return evaluations


def _ensure_player_discard_tracking(game: PokaJanGame) -> None:
    """
    既存ゲームにプレイヤー別捨て牌履歴を追加。
    """
    if not hasattr(game, "player_discards"):
        game.player_discards = {
            i: []
            for i in range(4)
        }


def play_turn_with_discard_tracking(
    game: PokaJanGame,
) -> None:
    """
    v15用:
    元のplay_turnと同等だが、誰が何を切ったかも保存する。

    今後本体へ統合する前段階として、
    まず履歴機能を独立実装。
    """
    if game.is_finished():
        return

    _ensure_player_discard_tracking(game)

    i = game.turn_index
    player = game.players[i]
    agent = game.agents[i]
    game.turn_count += 1

    drawn = game.draw_cards(player, 1)

    if game.is_finished():
        return

    game.resolve_self_draw_roles(i)

    if game.is_finished():
        return

    if not player.hand:
        return

    discarded = agent.choose_discard(
        game,
        i,
    )

    player.hand.remove(discarded)
    game.discards.append(discarded)
    game.player_discards[i].append(
        discarded
    )

    game.resolve_discard_claims(
        i,
        discarded,
    )

    if not game.is_finished():
        game.turn_index = (
            game.turn_index + 1
        ) % 4


def history_demo(
    seed: int = 17,
    pre_turns: int = 8,
    simulations_per_card: int = 30,
) -> None:
    """
    数ターン実際に進めて捨て牌履歴を作った後、
    その履歴を使って打牌を評価するデモ。
    """
    game = PokaJanGame(
        seed=seed,
        starting_coins=1000,
        agents=[
            DeterminizedRolloutAgent()
            for _ in range(4)
        ],
        verbose=False,
    )

    _ensure_player_discard_tracking(game)

    # 数ターン進めて履歴を作る
    for _ in range(pre_turns):
        if game.is_finished():
            break
        play_turn_with_discard_tracking(
            game
        )

    # 現在手番のプレイヤーを打牌直前まで進める
    i = game.turn_index
    player = game.players[i]

    game.draw_cards(player, 1)

    if not game.is_finished():
        game.resolve_self_draw_roles(i)

    rows = evaluate_discards_history_monte_carlo(
        game,
        i,
        simulations_per_card=simulations_per_card,
        seed=999,
    )

    print("\n=== v15 捨て牌履歴つきモンテカルロ ===")
    print("登場グループ:", game.selected_groups)
    print("ボーナス:", game.bonus_member)
    print("手番:", player.name)

    print("\n各プレイヤーの捨て牌:")
    for pidx in range(4):
        print(
            f"P{pidx+1}:",
            " / ".join(
                c.short()
                for c in game.player_discards[pidx]
            )
            or "(なし)"
        )

    print("\n推奨打牌:")
    for rank, row in enumerate(rows, 1):
        sign = "+" if row.expected_coin_change >= 0 else ""
        print(
            f"{rank:>2}. {row.card.short():<30}"
            f" 平均最終={row.average_final_coins:7.1f}"
            f" 期待増減={sign}{row.expected_coin_change:7.1f}"
            f" 0点率={row.zero_rate:6.1%}"
        )



# ============================================================
# 自己対戦によるヒューリスティック重み探索（v16）
# ============================================================

@dataclass(frozen=True)
class AgentConfig:
    """
    HeuristicAgent の主要4パラメータ。
    """
    role_score_weight: float = 1.0
    future_role_weight: float = 1.0
    bonus_keep_weight: float = 35.0
    danger_weight: float = 1.0

    def make_agent(self) -> HeuristicAgent:
        return HeuristicAgent(
            role_score_weight=self.role_score_weight,
            future_role_weight=self.future_role_weight,
            bonus_keep_weight=self.bonus_keep_weight,
            danger_weight=self.danger_weight,
        )


BASELINE_CONFIG = AgentConfig(
    role_score_weight=1.0,
    future_role_weight=1.0,
    bonus_keep_weight=35.0,
    danger_weight=1.0,
)


def evaluate_config_against_baseline(
    candidate: AgentConfig,
    games_per_seat: int = 25,
    seed: int = 20260808,
) -> dict:
    """
    candidate を P1→P2→P3→P4 と席替えしながら、
    残り3人を baseline として対戦させる。

    評価は順位ではなく、
    candidate の「最終コイン - 開始1000コイン」の平均。

    同じ seed 系列を各席で使うことで、席順差をある程度ならす。
    """
    master_rng = random.Random(seed)

    total_delta = 0.0
    total_final = 0.0
    total_games = 0
    zero_count = 0

    for candidate_seat in range(4):
        # 各席で同じ個数だけゲームを行う
        for _ in range(games_per_seat):
            game_seed = master_rng.randrange(10**18)

            agents = []
            for seat in range(4):
                if seat == candidate_seat:
                    agents.append(candidate.make_agent())
                else:
                    agents.append(BASELINE_CONFIG.make_agent())

            game = PokaJanGame(
                seed=game_seed,
                starting_coins=1000,
                agents=agents,
                verbose=False,
            )

            result = game.run()

            final_coins = game.players[candidate_seat].coins
            total_final += final_coins
            total_delta += final_coins - 1000
            total_games += 1

            if final_coins == 0:
                zero_count += 1

    return {
        "config": candidate,
        "games": total_games,
        "average_final_coins": total_final / total_games,
        "average_coin_change": total_delta / total_games,
        "zero_rate": zero_count / total_games,
    }


def random_agent_configs(
    count: int,
    seed: int = 12345,
) -> list[AgentConfig]:
    """
    ランダム探索用の候補を生成。
    baseline も必ず含める。
    """
    rng = random.Random(seed)

    configs = [BASELINE_CONFIG]

    for _ in range(max(0, count - 1)):
        configs.append(
            AgentConfig(
                role_score_weight=rng.uniform(0.6, 1.6),
                future_role_weight=rng.uniform(0.5, 1.8),
                bonus_keep_weight=rng.uniform(5.0, 90.0),
                danger_weight=rng.uniform(0.3, 2.2),
            )
        )

    return configs


def search_agent_weights(
    candidate_count: int = 12,
    games_per_seat: int = 15,
    seed: int = 20260808,
) -> list[dict]:
    """
    軽量なランダムサーチ。

    各候補を baseline と対戦させ、
    平均最終コインが高い順に並べる。

    これはニューラルネット学習ではなく、
    ヒューリスティックの自動チューニング。
    """
    configs = random_agent_configs(
        candidate_count,
        seed=seed,
    )

    results = []

    for idx, config in enumerate(configs):
        result = evaluate_config_against_baseline(
            config,
            games_per_seat=games_per_seat,
            seed=seed + idx * 100003,
        )
        results.append(result)

    results.sort(
        key=lambda r: (
            r["average_final_coins"],
            -r["zero_rate"],
        ),
        reverse=True,
    )

    return results


def print_weight_search(
    candidate_count: int = 12,
    games_per_seat: int = 15,
    seed: int = 20260808,
) -> list[dict]:
    results = search_agent_weights(
        candidate_count=candidate_count,
        games_per_seat=games_per_seat,
        seed=seed,
    )

    print("\n=== v16 ヒューリスティック重み探索 ===")
    print(
        f"候補数={candidate_count}, "
        f"各候補={games_per_seat}局×4席"
    )

    for rank, r in enumerate(results, 1):
        c = r["config"]
        print(
            f"{rank:>2}. "
            f"平均最終={r['average_final_coins']:7.1f} "
            f"期待増減={r['average_coin_change']:+7.1f} "
            f"0点率={r['zero_rate']:6.1%} | "
            f"role={c.role_score_weight:.3f} "
            f"future={c.future_role_weight:.3f} "
            f"bonus={c.bonus_keep_weight:.1f} "
            f"danger={c.danger_weight:.3f}"
        )

    return results


def training_demo() -> None:
    """
    まず動作確認しやすい小規模設定。
    本格探索では candidate_count と games_per_seat を増やす。
    """
    print_weight_search(
        candidate_count=8,
        games_per_seat=5,
        seed=20260808,
    )



# ============================================================
# 2段階パラメータ探索 + 最良AIの利用（v17）
# ============================================================

def mutate_config(
    base: AgentConfig,
    rng: random.Random,
    scale: float = 0.25,
) -> AgentConfig:
    """
    上位候補の近傍を探索するための微調整。
    """
    return AgentConfig(
        role_score_weight=max(
            0.1,
            base.role_score_weight
            * rng.uniform(1.0 - scale, 1.0 + scale),
        ),
        future_role_weight=max(
            0.1,
            base.future_role_weight
            * rng.uniform(1.0 - scale, 1.0 + scale),
        ),
        bonus_keep_weight=max(
            0.0,
            base.bonus_keep_weight
            * rng.uniform(1.0 - scale, 1.0 + scale),
        ),
        danger_weight=max(
            0.05,
            base.danger_weight
            * rng.uniform(1.0 - scale, 1.0 + scale),
        ),
    )


def dedupe_configs(
    configs: list[AgentConfig],
    ndigits: int = 4,
) -> list[AgentConfig]:
    seen = set()
    out = []

    for c in configs:
        key = (
            round(c.role_score_weight, ndigits),
            round(c.future_role_weight, ndigits),
            round(c.bonus_keep_weight, ndigits),
            round(c.danger_weight, ndigits),
        )
        if key not in seen:
            seen.add(key)
            out.append(c)

    return out


def evaluate_configs_common_seeds(
    configs: list[AgentConfig],
    games_per_seat: int = 20,
    seed: int = 20260808,
) -> list[dict]:
    """
    全候補を同じゲームseed群で評価する。

    これにより、
    「候補Aだけたまたま簡単な局面を引いた」
    という比較ノイズを減らす。
    """
    master_rng = random.Random(seed)

    # 各席・各試合で共通のseedを使う
    seat_seeds = {
        seat: [
            master_rng.randrange(10**18)
            for _ in range(games_per_seat)
        ]
        for seat in range(4)
    }

    results = []

    for config in configs:
        total_final = 0.0
        total_delta = 0.0
        total_games = 0
        zero_count = 0

        for candidate_seat in range(4):
            for game_seed in seat_seeds[candidate_seat]:
                agents = [
                    (
                        config.make_agent()
                        if seat == candidate_seat
                        else BASELINE_CONFIG.make_agent()
                    )
                    for seat in range(4)
                ]

                game = PokaJanGame(
                    seed=game_seed,
                    starting_coins=1000,
                    agents=agents,
                    verbose=False,
                )

                game.run()

                final_coins = game.players[
                    candidate_seat
                ].coins

                total_final += final_coins
                total_delta += final_coins - 1000
                total_games += 1

                if final_coins == 0:
                    zero_count += 1

        results.append({
            "config": config,
            "games": total_games,
            "average_final_coins": (
                total_final / total_games
            ),
            "average_coin_change": (
                total_delta / total_games
            ),
            "zero_rate": (
                zero_count / total_games
            ),
        })

    results.sort(
        key=lambda r: (
            r["average_final_coins"],
            -r["zero_rate"],
        ),
        reverse=True,
    )

    return results


def two_stage_weight_search(
    initial_candidates: int = 16,
    initial_games_per_seat: int = 10,
    top_k: int = 4,
    mutations_per_top: int = 5,
    refine_games_per_seat: int = 25,
    seed: int = 20260808,
) -> dict:
    """
    Stage 1:
      広くランダム探索

    Stage 2:
      上位候補の周辺を細かく探索

    最終評価:
      全候補を共通seedで比較し、
      平均最終コイン最大の設定をbest_configとする。
    """
    rng = random.Random(seed)

    # ---------- Stage 1 ----------
    initial = random_agent_configs(
        initial_candidates,
        seed=seed,
    )

    stage1 = evaluate_configs_common_seeds(
        initial,
        games_per_seat=initial_games_per_seat,
        seed=seed + 101,
    )

    elites = [
        r["config"]
        for r in stage1[:top_k]
    ]

    # ---------- Stage 2 ----------
    refined = list(elites)

    for elite in elites:
        for _ in range(mutations_per_top):
            refined.append(
                mutate_config(
                    elite,
                    rng,
                    scale=0.25,
                )
            )

    # baselineも比較対象に必ず入れる
    refined.append(BASELINE_CONFIG)

    refined = dedupe_configs(refined)

    stage2 = evaluate_configs_common_seeds(
        refined,
        games_per_seat=refine_games_per_seat,
        seed=seed + 202,
    )

    return {
        "stage1": stage1,
        "stage2": stage2,
        "best_config": stage2[0]["config"],
        "best_result": stage2[0],
    }


def print_two_stage_search(
    initial_candidates: int = 12,
    initial_games_per_seat: int = 6,
    top_k: int = 3,
    mutations_per_top: int = 4,
    refine_games_per_seat: int = 12,
    seed: int = 20260808,
) -> dict:
    result = two_stage_weight_search(
        initial_candidates=initial_candidates,
        initial_games_per_seat=initial_games_per_seat,
        top_k=top_k,
        mutations_per_top=mutations_per_top,
        refine_games_per_seat=refine_games_per_seat,
        seed=seed,
    )

    print("\n=== v17 2段階パラメータ探索 ===")

    print("\nStage 1 上位:")
    for rank, r in enumerate(
        result["stage1"][:5],
        1,
    ):
        c = r["config"]
        print(
            f"{rank:>2}. "
            f"平均最終={r['average_final_coins']:7.1f} "
            f"期待増減={r['average_coin_change']:+7.1f} | "
            f"role={c.role_score_weight:.3f} "
            f"future={c.future_role_weight:.3f} "
            f"bonus={c.bonus_keep_weight:.1f} "
            f"danger={c.danger_weight:.3f}"
        )

    print("\nStage 2 上位:")
    for rank, r in enumerate(
        result["stage2"][:8],
        1,
    ):
        c = r["config"]
        print(
            f"{rank:>2}. "
            f"平均最終={r['average_final_coins']:7.1f} "
            f"期待増減={r['average_coin_change']:+7.1f} "
            f"0点率={r['zero_rate']:6.1%} | "
            f"role={c.role_score_weight:.3f} "
            f"future={c.future_role_weight:.3f} "
            f"bonus={c.bonus_keep_weight:.1f} "
            f"danger={c.danger_weight:.3f}"
        )

    c = result["best_config"]

    print("\nBest config:")
    print(
        f"role_score_weight={c.role_score_weight:.6f}"
    )
    print(
        f"future_role_weight={c.future_role_weight:.6f}"
    )
    print(
        f"bonus_keep_weight={c.bonus_keep_weight:.6f}"
    )
    print(
        f"danger_weight={c.danger_weight:.6f}"
    )

    return result


class TunedRolloutAgent(HeuristicAgent):
    """
    探索で得たbest_configをロールアウトに使うためのラッパー。
    """

    def __init__(self, config: AgentConfig):
        super().__init__(
            role_score_weight=config.role_score_weight,
            future_role_weight=config.future_role_weight,
            bonus_keep_weight=config.bonus_keep_weight,
            danger_weight=config.danger_weight,
        )


def make_tuned_rollout_agents(
    config: AgentConfig,
) -> list[TunedRolloutAgent]:
    return [
        TunedRolloutAgent(config)
        for _ in range(4)
    ]


def compare_tuned_vs_baseline(
    tuned_config: AgentConfig,
    games_per_seat: int = 20,
    seed: int = 424242,
) -> dict:
    """
    tuned_config が baseline より本当に平均最終コインで上かを
    共通seed・全4席で再確認する。
    """
    configs = [
        tuned_config,
        BASELINE_CONFIG,
    ]

    results = evaluate_configs_common_seeds(
        configs,
        games_per_seat=games_per_seat,
        seed=seed,
    )

    return {
        "tuned": next(
            r for r in results
            if r["config"] == tuned_config
        ),
        "baseline": next(
            r for r in results
            if r["config"] == BASELINE_CONFIG
        ),
    }


def tuning_demo() -> None:
    result = print_two_stage_search(
        initial_candidates=8,
        initial_games_per_seat=4,
        top_k=2,
        mutations_per_top=3,
        refine_games_per_seat=6,
        seed=20260808,
    )

    print("\n=== Best vs Baseline 再確認 ===")
    comp = compare_tuned_vs_baseline(
        result["best_config"],
        games_per_seat=5,
        seed=777,
    )

    print(
        "Tuned   平均最終:",
        round(
            comp["tuned"]["average_final_coins"],
            1,
        ),
    )
    print(
        "Baseline平均最終:",
        round(
            comp["baseline"]["average_final_coins"],
            1,
        ),
    )



# ============================================================
# Tuned AI + 捨て牌履歴つき不完全情報モンテカルロ（v18）
# ============================================================

def _make_determinized_game_with_history_tuned(
    game: PokaJanGame,
    observer_index: int,
    seed: int,
    tuned_config: AgentConfig,
) -> PokaJanGame:
    """
    v15の捨て牌履歴つきdeterminizationに、
    v17で得たTuned AIをロールアウト役として組み込む。
    """
    rng = random.Random(seed)

    sim = copy.deepcopy(game)
    sim.rng = random.Random(seed)
    sim.verbose = False

    # ロールアウトはTuned AI
    sim.agents = [
        TunedRolloutAgent(tuned_config)
        for _ in range(4)
    ]

    pool = _cached_full_card_pool(
        tuple(game.selected_groups)
    )

    visible_cards = (
        list(game.players[observer_index].hand)
        + list(game.discards)
    )

    for card in visible_cards:
        pool.remove(card)

    opponent_indices = [
        i for i in range(4)
        if i != observer_index
    ]

    opponent_card_count = sum(
        len(game.players[i].hand)
        for i in opponent_indices
    )

    total_hidden_needed = (
        opponent_card_count
        + len(game.deck)
    )

    if total_hidden_needed > len(pool):
        raise RuntimeError(
            "公開情報とカードプールの整合性が取れません。"
        )

    # 現在ゲーム内に残っている未知カードを抽選
    hidden_in_play = rng.sample(
        pool,
        total_hidden_needed,
    )

    # 相手手札は捨て牌履歴を反映して割り当て
    sampled_hands, remaining_hidden = (
        _assign_hidden_hands_with_discard_bias(
            game,
            observer_index,
            hidden_in_play,
            opponent_indices,
            rng,
        )
    )

    for i in opponent_indices:
        sim.players[i].hand = list(
            sampled_hands[i]
        )

    # 観測者の手札は固定
    sim.players[observer_index].hand = list(
        game.players[observer_index].hand
    )

    # 残りは山札としてランダム順
    sampled_deck = list(remaining_hidden)
    rng.shuffle(sampled_deck)
    sim.deck = sampled_deck

    return sim


def evaluate_discards_tuned_history_mc(
    game: PokaJanGame,
    player_index: int,
    tuned_config: AgentConfig,
    simulations_per_card: int = 100,
    seed: int = 20260808,
) -> list[ImperfectMonteCarloEvaluation]:
    """
    v18の本命打牌評価。

    各打牌について:
      1. 捨て牌履歴を使って相手手札を推定
      2. 山札も再サンプリング
      3. Tuned AI 4人でゲーム終了までロールアウト
      4. 自分の最終コイン期待値を計算

    評価基準は平均最終コイン。
    """
    if simulations_per_card <= 0:
        raise ValueError(
            "simulations_per_card は1以上にしてください。"
        )

    player = game.players[player_index]
    current_coins = player.coins

    reps = {}
    for card in player.hand:
        reps.setdefault(
            (card.member, card.color),
            card,
        )

    master_rng = random.Random(seed)

    # 全打牌候補に同じworld seed列を使う
    world_seeds = [
        master_rng.randrange(10**18)
        for _ in range(simulations_per_card)
    ]

    evaluations = []

    for card in reps.values():
        finals = []

        for world_seed in world_seeds:
            sim = _make_determinized_game_with_history_tuned(
                game,
                observer_index=player_index,
                seed=world_seed,
                tuned_config=tuned_config,
            )

            _force_discard_and_rollout(
                sim,
                player_index,
                card,
            )

            finals.append(
                sim.players[player_index].coins
            )

        ordered = sorted(finals)
        n = len(ordered)

        if n % 2:
            median = ordered[n // 2]
        else:
            median = (
                ordered[n // 2 - 1]
                + ordered[n // 2]
            ) / 2

        avg = sum(ordered) / n

        evaluations.append(
            ImperfectMonteCarloEvaluation(
                card=card,
                simulations=n,
                average_final_coins=avg,
                expected_coin_change=avg-current_coins,
                median_final_coins=median,
                zero_rate=sum(
                    x == 0
                    for x in ordered
                ) / n,
                min_final_coins=min(ordered),
                max_final_coins=max(ordered),
            )
        )

    evaluations.sort(
        key=lambda e: (
            e.average_final_coins,
            e.median_final_coins,
            -e.zero_rate,
        ),
        reverse=True,
    )

    return evaluations


def print_tuned_history_mc(
    game: PokaJanGame,
    player_index: int,
    tuned_config: AgentConfig,
    simulations_per_card: int = 100,
    seed: int = 999,
) -> list[ImperfectMonteCarloEvaluation]:

    rows = evaluate_discards_tuned_history_mc(
        game,
        player_index,
        tuned_config=tuned_config,
        simulations_per_card=simulations_per_card,
        seed=seed,
    )

    print("\n=== v18 Tuned + 捨て牌履歴 MC ===")
    print("登場グループ:", game.selected_groups)
    print("ボーナス:", game.bonus_member)
    print(
        "現在コイン:",
        {p.name: p.coins for p in game.players}
    )

    print("\n各プレイヤーの捨て牌:")
    history = _discard_history_by_player(game)

    for i in range(4):
        print(
            f"P{i+1}:",
            " / ".join(
                c.short()
                for c in history[i]
            )
            or "(なし)"
        )

    print("\nTuned config:")
    print(
        f"role={tuned_config.role_score_weight:.3f}, "
        f"future={tuned_config.future_role_weight:.3f}, "
        f"bonus={tuned_config.bonus_keep_weight:.1f}, "
        f"danger={tuned_config.danger_weight:.3f}"
    )

    print(
        "\n対象手札:",
        " / ".join(
            c.short()
            for c in game.players[player_index].hand
        )
    )

    print(
        f"\n各打牌 {simulations_per_card} world"
    )

    for rank, row in enumerate(rows, 1):
        sign = "+" if row.expected_coin_change >= 0 else ""

        print(
            f"{rank:>2}. {row.card.short():<30}"
            f" 平均最終={row.average_final_coins:7.1f}"
            f" 期待増減={sign}{row.expected_coin_change:7.1f}"
            f" 中央値={row.median_final_coins:7.1f}"
            f" 0点率={row.zero_rate:6.1%}"
        )

    return rows


def train_then_analyze_demo(
    seed: int = 17,
    pre_turns: int = 8,
    simulations_per_card: int = 30,
) -> None:
    """
    1. 小規模2段階探索でTuned configを取得
    2. 数ターン進めて捨て牌履歴を作る
    3. Tuned + 履歴つきMCで打牌評価
    """
    print("=== Step 1: AIパラメータ探索 ===")

    search = two_stage_weight_search(
        initial_candidates=8,
        initial_games_per_seat=4,
        top_k=2,
        mutations_per_top=3,
        refine_games_per_seat=6,
        seed=20260808,
    )

    tuned_config = search["best_config"]

    print(
        "Best:",
        tuned_config,
    )

    print("\n=== Step 2: 局面生成 ===")

    game = PokaJanGame(
        seed=seed,
        starting_coins=1000,
        agents=[
            TunedRolloutAgent(tuned_config)
            for _ in range(4)
        ],
        verbose=False,
    )

    _ensure_player_discard_tracking(game)

    # 履歴生成
    for _ in range(pre_turns):
        if game.is_finished():
            break

        play_turn_with_discard_tracking(
            game
        )

    i = game.turn_index
    player = game.players[i]

    # 打牌直前へ
    game.draw_cards(player, 1)

    if not game.is_finished():
        game.resolve_self_draw_roles(i)

    print_tuned_history_mc(
        game,
        i,
        tuned_config=tuned_config,
        simulations_per_card=simulations_per_card,
        seed=999,
    )



# ============================================================
# 学習済み設定の保存・読込・即時解析（v19）
# ============================================================

DEFAULT_TUNED_CONFIG_PATH = "pokajan_tuned_config.json"


def save_agent_config(
    config: AgentConfig,
    path: str = DEFAULT_TUNED_CONFIG_PATH,
    metadata: dict | None = None,
) -> None:
    data = {
        "role_score_weight": config.role_score_weight,
        "future_role_weight": config.future_role_weight,
        "bonus_keep_weight": config.bonus_keep_weight,
        "danger_weight": config.danger_weight,
    }
    if metadata is not None:
        data["metadata"] = metadata

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_agent_config(
    path: str = DEFAULT_TUNED_CONFIG_PATH,
) -> AgentConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return AgentConfig(
        role_score_weight=float(data["role_score_weight"]),
        future_role_weight=float(data["future_role_weight"]),
        bonus_keep_weight=float(data["bonus_keep_weight"]),
        danger_weight=float(data["danger_weight"]),
    )


def train_and_save_config(
    output_path: str = DEFAULT_TUNED_CONFIG_PATH,
    initial_candidates: int = 24,
    initial_games_per_seat: int = 20,
    top_k: int = 5,
    mutations_per_top: int = 8,
    refine_games_per_seat: int = 50,
    seed: int = 20260808,
) -> dict:
    started = time.time()

    result = two_stage_weight_search(
        initial_candidates=initial_candidates,
        initial_games_per_seat=initial_games_per_seat,
        top_k=top_k,
        mutations_per_top=mutations_per_top,
        refine_games_per_seat=refine_games_per_seat,
        seed=seed,
    )

    best = result["best_config"]
    best_result = result["best_result"]
    elapsed = time.time() - started

    metadata = {
        "seed": seed,
        "initial_candidates": initial_candidates,
        "initial_games_per_seat": initial_games_per_seat,
        "top_k": top_k,
        "mutations_per_top": mutations_per_top,
        "refine_games_per_seat": refine_games_per_seat,
        "average_final_coins": best_result["average_final_coins"],
        "average_coin_change": best_result["average_coin_change"],
        "zero_rate": best_result["zero_rate"],
        "elapsed_seconds": elapsed,
    }

    save_agent_config(best, path=output_path, metadata=metadata)

    return {
        "config": best,
        "result": best_result,
        "metadata": metadata,
        "path": output_path,
    }


def analyze_with_saved_config(
    game: PokaJanGame,
    player_index: int,
    config_path: str = DEFAULT_TUNED_CONFIG_PATH,
    simulations_per_card: int = 100,
    seed: int = 999,
) -> list[ImperfectMonteCarloEvaluation]:
    tuned = load_agent_config(config_path)

    return evaluate_discards_tuned_history_mc(
        game,
        player_index,
        tuned_config=tuned,
        simulations_per_card=simulations_per_card,
        seed=seed,
    )


def print_saved_config_analysis(
    game: PokaJanGame,
    player_index: int,
    config_path: str = DEFAULT_TUNED_CONFIG_PATH,
    simulations_per_card: int = 100,
    seed: int = 999,
) -> list[ImperfectMonteCarloEvaluation]:
    tuned = load_agent_config(config_path)

    print(f"\nLoaded config: {config_path}")

    return print_tuned_history_mc(
        game,
        player_index,
        tuned_config=tuned,
        simulations_per_card=simulations_per_card,
        seed=seed,
    )


def make_history_game_for_analysis(
    seed: int = 17,
    pre_turns: int = 8,
    config: AgentConfig | None = None,
) -> tuple[PokaJanGame, int]:
    if config is None:
        config = BASELINE_CONFIG

    game = PokaJanGame(
        seed=seed,
        starting_coins=1000,
        agents=[TunedRolloutAgent(config) for _ in range(4)],
        verbose=False,
    )

    _ensure_player_discard_tracking(game)

    for _ in range(pre_turns):
        if game.is_finished():
            break
        play_turn_with_discard_tracking(game)

    i = game.turn_index
    player = game.players[i]

    game.draw_cards(player, 1)
    if not game.is_finished():
        game.resolve_self_draw_roles(i)

    return game, i


def v19_demo(
    config_path: str = DEFAULT_TUNED_CONFIG_PATH,
) -> None:
    print("=== Step 1: train & save ===")

    trained = train_and_save_config(
        output_path=config_path,
        initial_candidates=8,
        initial_games_per_seat=4,
        top_k=2,
        mutations_per_top=3,
        refine_games_per_seat=6,
        seed=20260808,
    )

    print("Saved best config:", trained["config"])
    print("JSON:", trained["path"])

    print("\n=== Step 2: load & analyze ===")

    cfg = load_agent_config(config_path)

    game, i = make_history_game_for_analysis(
        seed=17,
        pre_turns=8,
        config=cfg,
    )

    print_saved_config_analysis(
        game,
        i,
        config_path=config_path,
        simulations_per_card=20,
        seed=999,
    )



# ============================================================
# 本格チューニング専用モード（v20）
# ============================================================

def serious_training_run(
    output_path: str = DEFAULT_TUNED_CONFIG_PATH,
    seed: int = 20260808,
    initial_candidates: int = 30,
    initial_games_per_seat: int = 25,
    top_k: int = 6,
    mutations_per_top: int = 10,
    refine_games_per_seat: int = 60,
) -> dict:
    """
    本格チューニング用。

    目安の対局数:
      Stage1:
        initial_candidates × initial_games_per_seat × 4席
      Stage2:
        (top_k + top_k*mutations_per_top + baseline)
        × refine_games_per_seat × 4席

    かなり多くの自己対戦を行うため、
    普段の打牌解析とは分離して使う。
    """

    stage1_games = (
        initial_candidates
        * initial_games_per_seat
        * 4
    )

    stage2_candidates = (
        top_k
        + top_k * mutations_per_top
        + 1
    )

    stage2_games = (
        stage2_candidates
        * refine_games_per_seat
        * 4
    )

    estimated_total_games = (
        stage1_games + stage2_games
    )

    print("=== v20 本格チューニング ===")
    print(
        "Stage1想定局数:",
        stage1_games,
    )
    print(
        "Stage2想定局数:",
        stage2_games,
    )
    print(
        "合計想定局数:",
        estimated_total_games,
    )
    print()

    started = time.time()

    result = train_and_save_config(
        output_path=output_path,
        initial_candidates=initial_candidates,
        initial_games_per_seat=initial_games_per_seat,
        top_k=top_k,
        mutations_per_top=mutations_per_top,
        refine_games_per_seat=refine_games_per_seat,
        seed=seed,
    )

    elapsed = time.time() - started

    print("\n=== 学習完了 ===")
    print(
        "Best config:",
        result["config"],
    )
    print(
        "平均最終コイン:",
        round(
            result["result"]["average_final_coins"],
            2,
        ),
    )
    print(
        "期待増減:",
        round(
            result["result"]["average_coin_change"],
            2,
        ),
    )
    print(
        "0点率:",
        f"{result['result']['zero_rate']:.2%}",
    )
    print(
        "実測秒数:",
        round(elapsed, 2),
    )
    print(
        "保存先:",
        output_path,
    )

    return result


def quick_training_run(
    output_path: str = DEFAULT_TUNED_CONFIG_PATH,
    seed: int = 20260808,
) -> dict:
    """
    動作確認用の軽量版。
    """
    return serious_training_run(
        output_path=output_path,
        seed=seed,
        initial_candidates=8,
        initial_games_per_seat=4,
        top_k=2,
        mutations_per_top=3,
        refine_games_per_seat=6,
    )


def medium_training_run(
    output_path: str = DEFAULT_TUNED_CONFIG_PATH,
    seed: int = 20260808,
) -> dict:
    """
    中規模版。
    まず本格学習前に試す用途。
    """
    return serious_training_run(
        output_path=output_path,
        seed=seed,
        initial_candidates=16,
        initial_games_per_seat=10,
        top_k=4,
        mutations_per_top=6,
        refine_games_per_seat=20,
    )


def load_and_print_saved_config(
    path: str = DEFAULT_TUNED_CONFIG_PATH,
) -> AgentConfig:
    """
    保存済み設定だけ確認したいとき用。
    """
    cfg = load_agent_config(path)

    print("=== 保存済みTuned Config ===")
    print(
        f"role_score_weight={cfg.role_score_weight:.6f}"
    )
    print(
        f"future_role_weight={cfg.future_role_weight:.6f}"
    )
    print(
        f"bonus_keep_weight={cfg.bonus_keep_weight:.6f}"
    )
    print(
        f"danger_weight={cfg.danger_weight:.6f}"
    )

    return cfg

# ============================================================
# 実戦局面 手入力解析モード（v21）
# ============================================================

COLOR_ALIASES = {
    "橙": "orange",
    "オレンジ": "orange",
    "orange": "orange",
    "o": "orange",
    "青": "blue",
    "ブルー": "blue",
    "blue": "blue",
    "b": "blue",
    "桃": "pink",
    "ピンク": "pink",
    "pink": "pink",
    "p": "pink",
}

GROUP_ALIASES = {
    "0期生": "JP0", "JP0期生": "JP0",
    "1期生": "JP1", "JP1期生": "JP1",
    "2期生": "JP2", "JP2期生": "JP2",
    "ゲーマーズ": "GAMERS", "GAMERS": "GAMERS",
    "3期生": "JP3", "JP3期生": "JP3",
    "4期生": "JP4", "JP4期生": "JP4",
    "5期生": "JP5", "JP5期生": "JP5",
    "holoX": "HOLOX", "HOLOX": "HOLOX",
    "ReGLOSS": "REGLOSS", "REGLOSS": "REGLOSS",
    "Myth": "MYTH", "MYTH": "MYTH",
    "Advent": "ADVENT", "ADVENT": "ADVENT",
    "Promise": "PROMISE", "PROMISE": "PROMISE",
    "ID1期生": "ID1", "ID1": "ID1",
    "ID2期生": "ID2", "ID2": "ID2",
    "ID3期生": "ID3", "ID3": "ID3",
}


def normalize_group_name(text: str) -> str:
    t = text.strip()
    if t in GROUPS:
        return t
    if t in GROUP_ALIASES:
        return GROUP_ALIASES[t]
    raise ValueError(f"不明なグループ名です: {text}")


def normalize_member_name(
    text: str,
    selected_groups: tuple[str, ...],
) -> str:
    """
    完全一致を基本にしつつ、空白除去後の一意一致も許可。
    """
    raw = text.strip()
    active = members_in_groups(selected_groups)

    if raw in active:
        return raw

    compact = raw.replace(" ", "").replace("　", "")
    matches = [
        m for m in active
        if m.replace(" ", "").replace("　", "") == compact
    ]

    if len(matches) == 1:
        return matches[0]

    raise ValueError(
        f"登場メンバーに '{text}' が見つかりません。"
    )


def parse_card_token(
    token: str,
    selected_groups: tuple[str, ...],
    used_counts: dict[tuple[str, str], int],
) -> Card:
    """
    入力形式:
      兎田ぺこら:橙
      兎田ぺこら,橙
      兎田ぺこら/橙

    copy_no はユーザーが入力しなくてよい。
    同じmember/colorが見えるたびに1,2,3を自動付与する。
    """
    token = token.strip()

    parts = re.split(r"[:：,/／]", token)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) != 2:
        raise ValueError(
            f"カード '{token}' は「ホロメン名:色」で入力してください。"
        )

    member_raw, color_raw = parts

    member = normalize_member_name(
        member_raw,
        selected_groups,
    )

    color_key = color_raw.lower()
    color = (
        COLOR_ALIASES.get(color_raw)
        or COLOR_ALIASES.get(color_key)
    )

    if color is None:
        raise ValueError(
            f"不明な色です: {color_raw}"
        )

    key = (member, color)
    copy_no = used_counts.get(key, 0) + 1

    if copy_no > 3:
        raise ValueError(
            f"{member}の{color_raw}は3枚までです。"
        )

    used_counts[key] = copy_no
    return Card(member, color, copy_no)


def parse_card_list(
    text: str,
    selected_groups: tuple[str, ...],
    used_counts: dict[tuple[str, str], int],
) -> list[Card]:
    """
    カード同士は ; または | で区切る。
    空欄なら空リスト。
    """
    text = text.strip()
    if not text:
        return []

    tokens = re.split(r"[;；|｜\n]+", text)

    return [
        parse_card_token(
            token,
            selected_groups,
            used_counts,
        )
        for token in tokens
        if token.strip()
    ]


def _manual_public_removed_cards(
    game: PokaJanGame,
) -> list[Card]:
    return list(
        getattr(game, "public_removed_cards", [])
    )


def _all_public_visible_cards_for_observer(
    game: PokaJanGame,
    observer_index: int,
) -> list[Card]:
    """
    observerが確実に知っているカード。
    """
    return (
        list(game.players[observer_index].hand)
        + list(game.discards)
        + _manual_public_removed_cards(game)
    )


def build_manual_game_state(
    selected_groups: tuple[str, ...],
    bonus_member: str,
    coins: tuple[int, int, int, int],
    player_index: int,
    hand: list[Card],
    player_discards: dict[int, list[Card]],
    deck_remaining: int,
    public_removed_cards: list[Card] | None = None,
    turn_count: int = 0,
    seed: int = 17,
) -> PokaJanGame:
    """
    実際の局面を解析用PokaJanGameへ変換する。

    注意:
    - player_index の手札だけ実データを保持。
    - 相手手札は枚数7枚のダミー状態にし、
      MC開始時に公開情報から再サンプリングする。
    - 打牌直前を想定するため、自分の手札は通常8枚。
    """
    selected_groups = tuple(
        normalize_group_name(g)
        for g in selected_groups
    )

    if len(selected_groups) != 4:
        raise ValueError(
            "登場グループは4組入力してください。"
        )

    if not groups_are_compatible(selected_groups):
        raise ValueError(
            "JP1期生とゲーマーズは同時に登場できません。"
        )

    active_members = members_in_groups(
        selected_groups
    )

    if bonus_member not in active_members:
        raise ValueError(
            "ボーナスホロメンが登場4グループに含まれていません。"
        )

    if not 0 <= player_index < 4:
        raise ValueError(
            "自分の席は1〜4で指定してください。"
        )

    if len(hand) != 8:
        raise ValueError(
            f"打牌直前の自分の手札は8枚必要です（現在{len(hand)}枚）。"
        )

    if deck_remaining < 0 or deck_remaining > 100:
        raise ValueError(
            "残り山札枚数は0〜100です。"
        )

    if any(c < 0 for c in coins):
        raise ValueError(
            "コインは0未満にできません。"
        )

    # ベースGameを作って構造だけ利用
    game = PokaJanGame(
        seed=seed,
        starting_coins=1000,
        selected_groups=selected_groups,
        agents=[
            DeterminizedRolloutAgent()
            for _ in range(4)
        ],
        verbose=False,
    )

    game.selected_groups = selected_groups
    game.active_members = active_members
    game.bonus_member = bonus_member
    game.turn_index = player_index
    game.turn_count = turn_count

    for i in range(4):
        game.players[i].coins = int(coins[i])

    game.players[player_index].hand = list(hand)

    # 相手の具体的な手札は解析時に再構成するため、
    # 枚数だけ7枚相当で保持する。
    # 実Cardを置くと公開カードと誤認する可能性があるため、
    # hidden_hand_sizesを別途持つ。
    game.hidden_hand_sizes = {
        i: (
            len(hand)
            if i == player_index
            else 7
        )
        for i in range(4)
    }

    # 相手handそのものは空にしておく。
    for i in range(4):
        if i != player_index:
            game.players[i].hand = []

    game.player_discards = {
        i: list(player_discards.get(i, []))
        for i in range(4)
    }

    game.discards = []
    for i in range(4):
        game.discards.extend(
            game.player_discards[i]
        )

    game.public_removed_cards = list(
        public_removed_cards or []
    )

    # 山札は中身未知。枚数だけ必要なのでplaceholderを使わず
    # manual_deck_remainingとして保持する。
    game.manual_deck_remaining = int(
        deck_remaining
    )
    game.deck = [None] * deck_remaining

    return game


def _manual_opponent_hand_size(
    game: PokaJanGame,
    player_index: int,
) -> int:
    if hasattr(game, "hidden_hand_sizes"):
        return int(
            game.hidden_hand_sizes.get(
                player_index,
                7,
            )
        )
    return len(game.players[player_index].hand)


def _manual_deck_size(
    game: PokaJanGame,
) -> int:
    if hasattr(game, "manual_deck_remaining"):
        return int(game.manual_deck_remaining)
    return len(game.deck)


def _make_manual_determinized_game(
    game: PokaJanGame,
    observer_index: int,
    seed: int,
    tuned_config: AgentConfig,
) -> PokaJanGame:
    """
    手入力局面専用determinization。
    相手手札と山札を、公開情報 + 捨て牌履歴から作る。
    """
    rng = random.Random(seed)

    sim = copy.deepcopy(game)
    sim.rng = random.Random(seed)
    sim.verbose = False
    sim.agents = [
        TunedRolloutAgent(tuned_config)
        for _ in range(4)
    ]

    pool = _cached_full_card_pool(
        tuple(game.selected_groups)
    )

    visible_cards = (
        _all_public_visible_cards_for_observer(
            game,
            observer_index,
        )
    )

    for card in visible_cards:
        pool.remove(card)

    opponent_indices = [
        i for i in range(4)
        if i != observer_index
    ]

    opponent_hand_count = sum(
        _manual_opponent_hand_size(
            game,
            i,
        )
        for i in opponent_indices
    )

    deck_count = _manual_deck_size(game)

    total_hidden_needed = (
        opponent_hand_count
        + deck_count
    )

    if total_hidden_needed > len(pool):
        raise RuntimeError(
            "入力した公開カード・手札枚数・山札枚数の整合性が取れません。"
        )

    # 「100枚採用外 + 役で既に消えた未知カード」の可能性を残しつつ
    # 現在ゲーム内に必要な未知カードだけ選ぶ。
    hidden_in_play = rng.sample(
        pool,
        total_hidden_needed,
    )

    sampled_hands = {}
    remaining = list(hidden_in_play)

    # 各相手に捨て牌履歴バイアスを付けて配る
    for opponent_index in opponent_indices:
        n = _manual_opponent_hand_size(
            game,
            opponent_index,
        )

        weights = [
            _discard_based_weight(
                game,
                opponent_index,
                card,
            )
            for card in remaining
        ]

        hand_i = _weighted_sample_without_replacement(
            remaining,
            weights,
            n,
            rng,
        )

        sampled_hands[opponent_index] = hand_i

        for card in hand_i:
            remaining.remove(card)

    for i in opponent_indices:
        sim.players[i].hand = list(
            sampled_hands[i]
        )

    sim.players[observer_index].hand = list(
        game.players[observer_index].hand
    )

    rng.shuffle(remaining)
    sim.deck = list(remaining)
    sim.manual_deck_remaining = len(
        remaining
    )

    return sim


def evaluate_manual_position(
    game: PokaJanGame,
    player_index: int,
    tuned_config: AgentConfig,
    simulations_per_card: int = 200,
    seed: int = 999,
) -> list[ImperfectMonteCarloEvaluation]:
    """
    手入力局面の全打牌を最終コイン期待値で比較。
    """
    player = game.players[player_index]
    current_coins = player.coins

    reps = {}
    for card in player.hand:
        reps.setdefault(
            (card.member, card.color),
            card,
        )

    rng = random.Random(seed)
    world_seeds = [
        rng.randrange(10**18)
        for _ in range(simulations_per_card)
    ]

    evaluations = []

    for card in reps.values():
        finals = []

        for world_seed in world_seeds:
            sim = _make_manual_determinized_game(
                game,
                observer_index=player_index,
                seed=world_seed,
                tuned_config=tuned_config,
            )

            _force_discard_and_rollout(
                sim,
                player_index,
                card,
            )

            finals.append(
                sim.players[player_index].coins
            )

        ordered = sorted(finals)
        n = len(ordered)
        avg = sum(ordered) / n

        if n % 2:
            median = ordered[n // 2]
        else:
            median = (
                ordered[n // 2 - 1]
                + ordered[n // 2]
            ) / 2

        evaluations.append(
            ImperfectMonteCarloEvaluation(
                card=card,
                simulations=n,
                average_final_coins=avg,
                expected_coin_change=avg-current_coins,
                median_final_coins=median,
                zero_rate=sum(x == 0 for x in ordered)/n,
                min_final_coins=min(ordered),
                max_final_coins=max(ordered),
            )
        )

    evaluations.sort(
        key=lambda e: (
            e.average_final_coins,
            e.median_final_coins,
            -e.zero_rate,
        ),
        reverse=True,
    )

    return evaluations


def print_manual_analysis(
    game: PokaJanGame,
    player_index: int,
    tuned_config: AgentConfig,
    simulations_per_card: int = 200,
    seed: int = 999,
) -> list[ImperfectMonteCarloEvaluation]:

    rows = evaluate_manual_position(
        game,
        player_index,
        tuned_config,
        simulations_per_card=simulations_per_card,
        seed=seed,
    )

    print("\n=== 実戦局面 打牌解析 ===")
    print(
        "登場グループ:",
        game.selected_groups,
    )
    print(
        "ボーナス:",
        game.bonus_member,
    )
    print(
        "残り山札:",
        _manual_deck_size(game),
    )
    print(
        "コイン:",
        {p.name: p.coins for p in game.players},
    )
    print(
        "自分の手札:",
        " / ".join(
            c.short()
            for c in game.players[player_index].hand
        ),
    )

    print("\n推奨打牌:")
    for rank, row in enumerate(rows, 1):
        sign = "+" if row.expected_coin_change >= 0 else ""
        print(
            f"{rank:>2}. {row.card.short():<30}"
            f" 平均最終={row.average_final_coins:7.1f}"
            f" 期待増減={sign}{row.expected_coin_change:7.1f}"
            f" 中央値={row.median_final_coins:7.1f}"
            f" 0点率={row.zero_rate:6.1%}"
        )

    return rows


def _input_int(
    prompt: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            x = int(raw)
        except ValueError:
            print("整数で入力してください。")
            continue

        if minimum is not None and x < minimum:
            print(f"{minimum}以上で入力してください。")
            continue

        if maximum is not None and x > maximum:
            print(f"{maximum}以下で入力してください。")
            continue

        return x


def interactive_manual_analysis(
    config_path: str = DEFAULT_TUNED_CONFIG_PATH,
    simulations_per_card: int = 200,
) -> None:
    """
    ターミナルで実際の局面を手入力するモード。

    カード入力例:
      兎田ぺこら:橙; 宝鐘マリン:青; 不知火フレア:青

    カード同士は ; で区切る。
    """
    print("=== ポカじゃん 実戦局面解析 ===")
    print()

    print("使用できるグループコード:")
    print(
        "JP0 JP1 JP2 GAMERS JP3 JP4 JP5 "
        "HOLOX REGLOSS MYTH ADVENT PROMISE ID1 ID2 ID3"
    )

    group_raw = input(
        "登場4グループをカンマ区切りで入力: "
    )
    selected_groups = tuple(
        normalize_group_name(x)
        for x in re.split(r"[,，]", group_raw)
        if x.strip()
    )

    if len(selected_groups) != 4:
        raise ValueError(
            "グループは4組必要です。"
        )

    bonus_raw = input(
        "ボーナスホロメン名: "
    ).strip()
    bonus_member = normalize_member_name(
        bonus_raw,
        selected_groups,
    )

    player_index = (
        _input_int(
            "自分の席 (1～4): ",
            1,
            4,
        )
        - 1
    )

    coins = tuple(
        _input_int(
            f"P{i+1} の現在コイン: ",
            0,
        )
        for i in range(4)
    )

    deck_remaining = _input_int(
        "残り山札枚数: ",
        0,
        100,
    )

    used_counts = {}

    hand_text = input(
        "自分の8枚手札 (; 区切り、例 兎田ぺこら:橙;宝鐘マリン:青): "
    )
    hand = parse_card_list(
        hand_text,
        selected_groups,
        used_counts,
    )

    player_discards = {}

    for i in range(4):
        text = input(
            f"P{i+1} の捨て牌 (; 区切り、なければEnter): "
        )
        player_discards[i] = parse_card_list(
            text,
            selected_groups,
            used_counts,
        )

    removed_text = input(
        "役で既に消えた公開カード (; 区切り、分からなければEnter): "
    )
    public_removed_cards = parse_card_list(
        removed_text,
        selected_groups,
        used_counts,
    )

    game = build_manual_game_state(
        selected_groups=selected_groups,
        bonus_member=bonus_member,
        coins=coins,
        player_index=player_index,
        hand=hand,
        player_discards=player_discards,
        deck_remaining=deck_remaining,
        public_removed_cards=public_removed_cards,
        seed=17,
    )

    tuned_config = load_agent_config(
        config_path
    )

    print_manual_analysis(
        game,
        player_index,
        tuned_config=tuned_config,
        simulations_per_card=simulations_per_card,
        seed=999,
    )


def manual_demo_state() -> tuple[PokaJanGame, int]:
    """
    入力UIを毎回手打ちせず動作確認するための固定局面。
    """
    groups = (
        "JP3",
        "ADVENT",
        "PROMISE",
        "ID3",
    )

    used = {}

    hand = parse_card_list(
        (
            "兎田ぺこら:橙;"
            "古石ビジュー:桃;"
            "宝鐘マリン:青;"
            "不知火フレア:青;"
            "こぼ・かなえる:青;"
            "宝鐘マリン:橙;"
            "ベスティア・ゼータ:青;"
            "モココ・アビスガード:青"
        ),
        groups,
        used,
    )

    discards = {
        0: parse_card_list(
            "シオリ・ノヴェラ:桃",
            groups,
            used,
        ),
        1: parse_card_list(
            "フワワ・アビスガード:橙",
            groups,
            used,
        ),
        2: [],
        3: [],
    }

    game = build_manual_game_state(
        selected_groups=groups,
        bonus_member="七詩ムメイ",
        coins=(1000, 820, 1210, 970),
        player_index=0,
        hand=hand,
        player_discards=discards,
        deck_remaining=60,
        public_removed_cards=[],
        seed=17,
    )

    return game, 0



# ============================================================
# v24: 簡易入力モード
# ============================================================

SHORT_COLOR_ALIASES = {
    "o": "orange",
    "橙": "orange",
    "b": "blue",
    "青": "blue",
    "p": "pink",
    "桃": "pink",
}


def make_member_number_map(
    selected_groups: tuple[str, ...],
) -> tuple[dict[int, str], dict[str, int]]:
    """
    登場4グループのホロメンへ1から連番を振る。
    白上フブキのように複数所属しても重複しない。
    """
    members = members_in_groups(selected_groups)

    number_to_member = {
        i + 1: member
        for i, member in enumerate(members)
    }
    member_to_number = {
        member: number
        for number, member in number_to_member.items()
    }

    return number_to_member, member_to_number


def print_numbered_members(
    selected_groups: tuple[str, ...],
) -> dict[int, str]:
    number_to_member, _ = make_member_number_map(
        selected_groups
    )

    print("\n=== 今回のホロメン番号 ===")

    for group in selected_groups:
        print(f"\n[{group}]")
        for member in GROUPS[group]:
            # 重複所属メンバーも同じ番号を表示
            number = next(
                n for n, m in number_to_member.items()
                if m == member
            )
            print(
                f"{number:>2}: {member}"
            )

    print(
        "\n色: o=橙 / b=青 / p=桃"
    )
    print(
        "入力例: 3b;7o;12p"
    )

    return number_to_member


def parse_short_card_token(
    token: str,
    selected_groups: tuple[str, ...],
    number_to_member: dict[int, str],
    used_counts: dict[tuple[str, str], int],
) -> Card:
    """
    簡易形式:
      3b
      7o
      12p

    日本語色も可:
      3青
      7橙
      12桃
    """
    token = token.strip().lower()

    match = re.fullmatch(
        r"(\d+)\s*([obp]|橙|青|桃)",
        token,
    )

    if not match:
        raise ValueError(
            f"'{token}' は 3b / 7o / 12p のように入力してください。"
        )

    member_number = int(
        match.group(1)
    )
    color_raw = match.group(2)

    if member_number not in number_to_member:
        raise ValueError(
            f"ホロメン番号 {member_number} は存在しません。"
        )

    member = number_to_member[
        member_number
    ]

    color = SHORT_COLOR_ALIASES[
        color_raw
    ]

    key = (
        member,
        color,
    )
    copy_no = (
        used_counts.get(key, 0)
        + 1
    )

    if copy_no > 3:
        raise ValueError(
            f"{member}の{color_raw}は3枚までです。"
        )

    used_counts[key] = copy_no

    return Card(
        member,
        color,
        copy_no,
    )


def parse_short_card_list(
    text: str,
    selected_groups: tuple[str, ...],
    number_to_member: dict[int, str],
    used_counts: dict[tuple[str, str], int],
) -> list[Card]:
    text = text.strip()

    if not text:
        return []

    tokens = re.split(
        r"[;；,\s]+",
        text,
    )

    return [
        parse_short_card_token(
            token,
            selected_groups,
            number_to_member,
            used_counts,
        )
        for token in tokens
        if token.strip()
    ]


def choose_groups_simple() -> tuple[str, ...]:
    """
    グループも番号で選べるようにする。
    """
    group_codes = [
        "JP0",
        "JP1",
        "JP2",
        "GAMERS",
        "JP3",
        "JP4",
        "JP5",
        "HOLOX",
        "REGLOSS",
        "MYTH",
        "ADVENT",
        "PROMISE",
        "ID1",
        "ID2",
        "ID3",
    ]

    print("=== グループ一覧 ===")

    for i, group in enumerate(
        group_codes,
        1,
    ):
        print(
            f"{i:>2}: {group}"
        )

    while True:
        raw = input(
            "\n登場4グループの番号 "
            "(例 5,11,12,15): "
        )

        try:
            nums = [
                int(x)
                for x in re.split(
                    r"[,，\s]+",
                    raw.strip(),
                )
                if x
            ]
        except ValueError:
            print(
                "番号で入力してください。"
            )
            continue

        if (
            len(nums) != 4
            or len(set(nums)) != 4
        ):
            print(
                "異なる4グループを選んでください。"
            )
            continue

        if any(
            n < 1 or n > len(group_codes)
            for n in nums
        ):
            print(
                "一覧にある番号を選んでください。"
            )
            continue

        groups = tuple(
            group_codes[n - 1]
            for n in nums
        )

        if not groups_are_compatible(
            groups
        ):
            print(
                "JP1とGAMERSは同時に選べません。"
            )
            continue

        return groups


def choose_bonus_simple(
    number_to_member: dict[int, str],
) -> str:
    while True:
        number = _input_int(
            "ボーナスホロメン番号: ",
            1,
            max(number_to_member),
        )

        if number in number_to_member:
            return number_to_member[number]

        print(
            "存在するホロメン番号を入力してください。"
        )


def interactive_quick_analysis(
    config_path: str = DEFAULT_TUNED_CONFIG_PATH,
    simulations_per_card: int = 100,
) -> None:
    """
    v24 簡易入力版。

    入力の中心を
      ホロメン番号 + 色1文字
    に短縮する。
    """
    print(
        "=== ポカじゃん 簡易局面解析 ===\n"
    )

    selected_groups = (
        choose_groups_simple()
    )

    number_to_member = (
        print_numbered_members(
            selected_groups
        )
    )

    bonus_member = (
        choose_bonus_simple(
            number_to_member
        )
    )

    player_index = (
        _input_int(
            "\n自分の席 (1～4): ",
            1,
            4,
        )
        - 1
    )

    coins = tuple(
        _input_int(
            f"P{i+1} コイン: ",
            0,
        )
        for i in range(4)
    )

    deck_remaining = (
        _input_int(
            "残り山札枚数: ",
            0,
            100,
        )
    )

    used_counts = {}

    while True:
        hand_text = input(
            "\n自分の8枚 "
            "(例 3b;7o;12p...): "
        )

        try:
            hand = parse_short_card_list(
                hand_text,
                selected_groups,
                number_to_member,
                used_counts,
            )

            if len(hand) != 8:
                raise ValueError(
                    f"8枚必要です。現在{len(hand)}枚です。"
                )

            break

        except ValueError as e:
            print(
                "入力エラー:",
                e,
            )
            used_counts = {}

    player_discards = {}

    for i in range(4):
        while True:
            text = input(
                f"P{i+1} 捨て牌 "
                "(なければEnter): "
            )

            try:
                player_discards[i] = (
                    parse_short_card_list(
                        text,
                        selected_groups,
                        number_to_member,
                        used_counts,
                    )
                )
                break
            except ValueError as e:
                print(
                    "入力エラー:",
                    e,
                )

    while True:
        removed_text = input(
            "既に役で消えた公開カード "
            "(なければEnter): "
        )

        try:
            public_removed_cards = (
                parse_short_card_list(
                    removed_text,
                    selected_groups,
                    number_to_member,
                    used_counts,
                )
            )
            break
        except ValueError as e:
            print(
                "入力エラー:",
                e,
            )

    game = build_manual_game_state(
        selected_groups=selected_groups,
        bonus_member=bonus_member,
        coins=coins,
        player_index=player_index,
        hand=hand,
        player_discards=player_discards,
        deck_remaining=deck_remaining,
        public_removed_cards=public_removed_cards,
        seed=17,
    )

    tuned_config = (
        load_agent_config(
            config_path
        )
    )

    print_manual_analysis(
        game,
        player_index,
        tuned_config=tuned_config,
        simulations_per_card=simulations_per_card,
        seed=999,
    )


if __name__ == "__main__":
    interactive_quick_analysis(
        config_path="pokajan_tuned_config.json",
        simulations_per_card=100,
    )
