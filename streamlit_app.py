
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from pokajan_simulator_v24 import (
    AgentConfig,
    groups_are_compatible,
    make_member_number_map,
    build_manual_game_state,
    evaluate_manual_position,
    Card,
)

st.set_page_config(
    page_title="ポカジャンAI打牌解析｜ホロドリ",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1180px;
        padding-top: 1.2rem;
        padding-bottom: 2.5rem;
    }
    .hero {
        padding: 1.15rem 1.25rem;
        border: 1px solid rgba(128,128,128,.22);
        border-radius: 18px;
        margin-bottom: 1rem;
    }
    .hero-title {
        font-size: 1.8rem;
        font-weight: 800;
        margin-bottom: .25rem;
    }
    .hero-sub {
        opacity: .75;
        font-size: .95rem;
    }
    .hand-card {
        border: 1px solid rgba(128,128,128,.20);
        border-radius: 14px;
        padding: .65rem;
        margin-bottom: .5rem;
    }
    .recommend-box {
        border: 2px solid rgba(128,128,128,.35);
        border-radius: 20px;
        padding: 1.15rem 1.25rem;
        margin: 1rem 0;
    }
    .recommend-label {
        font-size: .9rem;
        opacity: .7;
        margin-bottom: .2rem;
    }
    .recommend-main {
        font-size: 1.75rem;
        font-weight: 800;
        line-height: 1.25;
        margin-bottom: .5rem;
    }
    .recommend-sub {
        font-size: 1rem;
        opacity: .85;
    }
    div[data-testid="stButton"] button {
        border-radius: 14px;
        min-height: 3rem;
        font-weight: 700;
    }
    div[data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,.18);
        border-radius: 14px;
        padding: .65rem .8rem;
    }
    @media (max-width: 768px) {
        .block-container {
            padding-left: .75rem;
            padding-right: .75rem;
        }
        .hero-title {
            font-size: 1.45rem;
        }
        .recommend-main {
            font-size: 1.4rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

COLOR_LABEL_TO_CODE = {"橙": "orange", "青": "blue", "桃": "pink"}

GROUP_OPTIONS = {
    "0期生": "JP0",
    "1期生": "JP1",
    "2期生": "JP2",
    "ゲーマーズ": "GAMERS",
    "3期生": "JP3",
    "4期生": "JP4",
    "5期生": "JP5",
    "holoX": "HOLOX",
    "ReGLOSS": "REGLOSS",
    "Myth": "MYTH",
    "Advent": "ADVENT",
    "Promise": "PROMISE",
    "ID1期生": "ID1",
    "ID2期生": "ID2",
    "ID3期生": "ID3",
}

DEFAULT_GROUP_LABELS = ["3期生", "Advent", "Promise", "ID3期生"]
DEFAULT_CONFIG_PATH = Path(__file__).with_name("pokajan_tuned_config.json")


def load_config():
    if not DEFAULT_CONFIG_PATH.exists():
        st.error(
            "pokajan_tuned_config.json が見つかりません。"
            "学習済みJSONをこのアプリと同じフォルダに置いてください。"
        )
        st.stop()

    data = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    return AgentConfig(
        role_score_weight=float(data["role_score_weight"]),
        future_role_weight=float(data["future_role_weight"]),
        bonus_keep_weight=float(data["bonus_keep_weight"]),
        danger_weight=float(data["danger_weight"]),
    )


def make_card(member, color_label, used_counts):
    color = COLOR_LABEL_TO_CODE[color_label]
    key = (member, color)
    copy_no = used_counts.get(key, 0) + 1

    if copy_no > 3:
        raise ValueError(f"{member}の{color_label}は3枚までです。")

    used_counts[key] = copy_no
    return Card(member, color, copy_no)


def card_picker(label, members, key_prefix, used_counts, default_member_index=0):
    st.markdown(
        f"<div class='hand-card'><b>{label}</b>",
        unsafe_allow_html=True,
    )

    member = st.selectbox(
        "ホロメン",
        members,
        index=min(default_member_index, len(members) - 1),
        key=f"{key_prefix}_member",
        label_visibility="collapsed",
        placeholder="ホロメン名を入力"
    )

    color = st.radio(
        "色",
        ["橙", "青", "桃"],
        horizontal=True,
        key=f"{key_prefix}_color",
        label_visibility="collapsed",
    )

    st.markdown("</div>", unsafe_allow_html=True)

    return make_card(member, color, used_counts)


config = load_config()

st.markdown(
    """
    <div class="hero">
      <div class="hero-title">ポカジャンAI打牌解析[ホロドリ]</div>
      <div class="hero-sub">
        ホロドリのミニゲーム「ポカジャン」の打牌をAIで解析するWebツールです。
        手札・捨て牌・コイン状況から、最終コイン期待値が高い打牌をシミュレーションします。
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("📘 使い方", expanded=False):
    st.markdown(
        """
        1. **登場する4グループ**を選びます。  
        2. **ボーナスホロメン**と自分の席を選びます。  
        3. 4人の**現在コイン**と**残り山札枚数**を入力します。  
        4. 自分の**8枚の手札**を入力します。  
        5. 分かる範囲で各プレイヤーの**捨て牌履歴**を入力します。  
        6. 必要なら、すでに役で消えた公開カードも入力します。  
        7. **「AIで解析する」**を押すと、各打牌の最終コイン期待値を比較します。
        """
    )

with st.expander("🎴 ポカジャンのルール", expanded=False):
    st.markdown(
        """
        - 4人対戦で、各プレイヤーは**1000コイン**からスタートします。
        - 通常時の手札は**7枚**で、自分のターンに1枚引いて8枚になります。
        - 役は、**同じホロメン3枚**または**同じグループのホロメンを1枚ずつ揃える役**です。
        - 役のカードがすべて同じ色なら、同色役として高得点になります。
        - 毎ゲーム、ボーナス対象のホロメンが1種類選ばれ、そのホロメンを役に含めると**1枚につき+90コイン**されます。
        - 自分のターンで成立した役は、他の3人から**3分の1ずつ**受け取ります。
        - 他人の捨て牌で役が完成した場合は、その捨てた人から得点を受け取ります。
        - 同じ捨て牌で複数人が同時に上がれる場合は、**最も得点の高い役が優先**されます。同点なら、捨てた人の次のプレイヤーから近い順に優先されます。
        - 誰かのコインが0になるか、山札が切れるとゲーム終了です。
        """
    )

with st.expander("🤖 AI解析について", expanded=False):
    st.markdown(
        """
        このツールは、見えていない相手の手札や山札を
        **複数のあり得る局面として推定**し、
        各打牌を選んだ後のゲームを繰り返しシミュレーションします。

        打牌の評価は**順位ではなく、最終的に自分が持っているコインの期待値**
        を基準にしています。

        - **平均最終コイン**：その打牌を選んだ場合の平均的な最終所持コイン
        - **期待増減**：現在のコインから平均でどれだけ増減するか
        - **中央値**：シミュレーション結果の中央値
        - **0点率**：最終的に0コインになった割合

        シミュレーション回数を増やすほど結果は安定しやすくなりますが、
        その分、解析にかかる時間も長くなります。

        ※解析結果はシミュレーションによる推定であり、
        必ずしも最善の打牌を保証するものではありません。
        """
    )

with st.expander("Simulation", expanded=False):
    simulations = st.slider(
        "How many simulation",
        min_value=20,
        max_value=500,
        value=25,
        step=20,
        help="多いほど結果は安定しますが、解析時間も長くなります。",
    )

st.markdown("## 1. ゲーム設定")

group_cols = st.columns(4)
selected_group_labels = []

option_labels = list(GROUP_OPTIONS.keys())

for i in range(4):
    label = group_cols[i].selectbox(
        f"登場グループ {i+1}",
        option_labels,
        index=option_labels.index(DEFAULT_GROUP_LABELS[i]),
        key=f"group_label_{i}",
    )
    selected_group_labels.append(label)

selected_groups = tuple(GROUP_OPTIONS[x] for x in selected_group_labels)

if len(set(selected_groups)) != 4:
    st.error("登場グループは4種類すべて別にしてください。")
    st.stop()

if not groups_are_compatible(selected_groups):
    st.error("1期生とゲーマーズは同時に登場できません。")
    st.stop()

number_to_member, _ = make_member_number_map(selected_groups)
members = list(number_to_member.values())

with st.expander("今回の登場ホロメン一覧", expanded=False):
    member_cols = st.columns(3)
    for idx, (number, member) in enumerate(number_to_member.items()):
        member_cols[idx % 3].write(f"**{number}.** {member}")

info_cols = st.columns([1.25, 1, 1])

bonus_member = info_cols[0].selectbox("ボーナスホロメン", members)

player_index = info_cols[1].selectbox(
    "自分の席",
    [0, 1, 2, 3],
    format_func=lambda x: f"P{x+1}",
)

deck_remaining = info_cols[2].number_input(
    "残り山札枚数",
    min_value=0,
    max_value=100,
    value=60,
    step=1,
)

st.markdown("### 現在コイン")
coin_cols = st.columns(4)

coins = tuple(
    int(
        coin_cols[i].number_input(
            f"P{i+1}",
            min_value=0,
            value=1000,
            step=10,
            key=f"coin_{i}",
        )
    )
    for i in range(4)
)

st.markdown("## 2. 自分の8枚手札")
st.caption("ホロメンを選び、下のボタンで色を指定してください。")

used_counts = {}
hand = []

row1 = st.columns(4)
for i in range(4):
    with row1[i]:
        try:
            hand.append(
                card_picker(
                    f"{i+1}枚目",
                    members,
                    f"hand_{i}",
                    used_counts,
                    default_member_index=i,
                )
            )
        except ValueError as e:
            st.error(str(e))
            st.stop()

row2 = st.columns(4)
for i in range(4, 8):
    with row2[i - 4]:
        try:
            hand.append(
                card_picker(
                    f"{i+1}枚目",
                    members,
                    f"hand_{i}",
                    used_counts,
                    default_member_index=i,
                )
            )
        except ValueError as e:
            st.error(str(e))
            st.stop()

st.markdown("## 3. 捨て牌履歴")

player_discards = {}
tabs = st.tabs(["P1", "P2", "P3", "P4"])

for p in range(4):
    with tabs[p]:
        n_discards = st.number_input(
            "捨て牌枚数",
            min_value=0,
            max_value=30,
            value=0,
            step=1,
            key=f"discard_count_{p}",
        )

        cards = []

        if int(n_discards) == 0:
            st.caption("捨て牌なし")

        for j in range(int(n_discards)):
            d1, d2 = st.columns([2.5, 1])

            member = d1.selectbox(
                f"{j+1}枚目 ホロメン",
                members,
                key=f"discard_member_{p}_{j}",
            )

            color = d2.selectbox(
                f"{j+1}枚目 色",
                ["橙", "青", "桃"],
                key=f"discard_color_{p}_{j}",
            )

            try:
                cards.append(make_card(member, color, used_counts))
            except ValueError as e:
                st.error(str(e))
                st.stop()

        player_discards[p] = cards

with st.expander("既に役で消えた公開カード（任意）", expanded=False):
    removed_count = st.number_input(
        "枚数",
        min_value=0,
        max_value=50,
        value=0,
        step=1,
        key="removed_count",
    )

    public_removed_cards = []

    for j in range(int(removed_count)):
        r1, r2 = st.columns([2.5, 1])

        member = r1.selectbox(
            f"{j+1}枚目 ホロメン",
            members,
            key=f"removed_member_{j}",
        )

        color = r2.selectbox(
            f"{j+1}枚目 色",
            ["橙", "青", "桃"],
            key=f"removed_color_{j}",
        )

        try:
            public_removed_cards.append(make_card(member, color, used_counts))
        except ValueError as e:
            st.error(str(e))
            st.stop()

st.markdown("## 4. AI解析")

if st.button("AIで解析する", type="primary", use_container_width=True):
    try:
        game = build_manual_game_state(
            selected_groups=selected_groups,
            bonus_member=bonus_member,
            coins=coins,
            player_index=player_index,
            hand=hand,
            player_discards=player_discards,
            deck_remaining=int(deck_remaining),
            public_removed_cards=public_removed_cards,
            seed=17,
        )

        with st.spinner("局面をシミュレーションしています..."):
            rows = evaluate_manual_position(
                game,
                player_index,
                tuned_config=config,
                simulations_per_card=int(simulations),
                seed=999,
            )

        best = rows[0]

        second_gap = None
        if len(rows) >= 2:
            second_gap = best.average_final_coins - rows[1].average_final_coins

        gap_html = ""
        if second_gap is not None:
            gap_html = f"<div class='recommend-sub'>2位との差 +{second_gap:.1f} コイン</div>"

        st.markdown(
            f"""
            <div class="recommend-box">
              <div class="recommend-label">推奨打牌</div>
              <div class="recommend-main">{best.card.short()}</div>
              <div class="recommend-sub">
                平均最終コイン {best.average_final_coins:.1f}
                ／ 期待増減 {best.expected_coin_change:+.1f}
              </div>
              {gap_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

        metric_cols = st.columns(3)

        metric_cols[0].metric(
            "平均最終コイン",
            f"{best.average_final_coins:.1f}",
        )

        metric_cols[1].metric(
            "期待増減",
            f"{best.expected_coin_change:+.1f}",
        )

        metric_cols[2].metric(
            "0点率",
            f"{best.zero_rate:.1%}",
        )

        st.markdown("### 全打牌ランキング")

        result_rows = []

        for rank, row in enumerate(rows, 1):
            result_rows.append(
                {
                    "順位": rank,
                    "打牌": row.card.short(),
                    "平均最終コイン": round(row.average_final_coins, 1),
                    "期待増減": round(row.expected_coin_change, 1),
                    "中央値": round(row.median_final_coins, 1),
                    "0点率": f"{row.zero_rate:.1%}",
                }
            )

        st.dataframe(
            pd.DataFrame(result_rows),
            hide_index=True,
            use_container_width=True,
        )

        with st.expander("解析の見方", expanded=False):
            st.write("「平均最終コイン」が最も高い打牌を最優先しています。")
            st.write("期待増減は、現在の自分のコインから平均で何コイン増減するかです。")
            st.write("シミュレーション回数を増やすと結果は安定しますが、解析時間は長くなります。")

    except Exception as e:
        st.error("解析中にエラーが発生しました。")
        st.exception(e)

st.divider()

st.caption(
    "※本サイトは非公式のファンメイドツールです。"
    "ホロライブおよび「ホロライブ ドリームス」と公式の関係はありません。"
    "解析結果はシミュレーションに基づく推定値です。"
)
