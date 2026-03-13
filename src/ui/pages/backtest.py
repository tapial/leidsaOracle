"""Backtest page — run walk-forward evaluation and view results."""

from __future__ import annotations

import httpx
import pandas as pd
import streamlit as st


def render(api_base: str):
    st.title("Backtesting Dashboard")

    st.info(
        "Walk-forward backtesting evaluates how the system's heuristic selections "
        "would have performed on historical draws it had never seen. "
        "Results are compared against random baselines."
    )

    game_type = st.selectbox("Game Type", ["loto", "loto_mas", "loto_pool"], key="bt_game")

    # Configuration
    col1, col2, col3, col4 = st.columns(4)
    train_window = col1.number_input("Train Window", 50, 500, 200)
    step_size = col2.number_input("Step Size", 1, 10, 1)
    combos_per_step = col3.number_input("Combos/Step", 1, 50, 10)
    max_steps = col4.number_input("Max Steps (0=all)", 0, 1000, 100)

    if st.button("Run Backtest", type="primary"):
        request = {
            "game_type": game_type,
            "train_window": train_window,
            "step_size": step_size,
            "combinations_per_step": combos_per_step,
        }
        if max_steps > 0:
            request["max_steps"] = max_steps

        with st.spinner("Running backtest... This may take a few minutes."):
            try:
                resp = httpx.post(
                    f"{api_base}/backtest/run",
                    json=request,
                    timeout=600,
                )
                if resp.status_code == 200:
                    st.session_state["bt_result"] = resp.json()
                    st.success("Backtest complete!")
                else:
                    st.error(f"Backtest failed: {resp.text}")
            except Exception as e:
                st.error(f"Error: {e}")

    # Display results
    result = st.session_state.get("bt_result")
    if not result:
        # Try to load latest
        try:
            resp = httpx.get(
                f"{api_base}/backtest/results",
                params={"game_type": game_type, "limit": 1},
                timeout=10,
            )
            if resp.status_code == 200:
                results_list = resp.json()
                if results_list:
                    result = results_list[0]
                    st.session_state["bt_result"] = result
        except Exception:
            pass

    if not result:
        st.info("No backtest results available. Run a backtest first.")
        return

    st.divider()

    # Summary
    summary = result.get("summary", {})
    st.subheader("Summary")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Steps", summary.get("total_steps", 0))
    col2.metric("Combos Evaluated", summary.get("total_combinations_evaluated", 0))
    col3.metric("Number Hit Rate", f"{summary.get('number_hit_rate', 0):.2%}")
    col4.metric(
        "vs Random",
        f"{summary.get('number_hit_improvement', 0):.2f}x",
        delta=f"Baseline: {summary.get('number_hit_baseline', 0):.2%}",
    )

    # Match distribution
    st.subheader("Match Distribution vs Random Baseline")
    metrics = result.get("metrics", {})
    match_dist = metrics.get("match_distribution", {})
    if match_dist:
        rows = []
        for k, v in match_dist.items():
            rows.append({
                "Match Level": int(k),
                "Actual Rate": v.get("actual_rate", 0),
                "Random Baseline": v.get("random_baseline", 0),
                "Improvement": v.get("improvement_factor", 0),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)

        # Chart
        chart_df = df[["Match Level", "Actual Rate", "Random Baseline"]].set_index("Match Level")
        st.bar_chart(chart_df)

    # Correlation
    st.subheader("Score-Performance Correlation")
    corr = summary.get("score_match_correlation", 0)
    p_val = summary.get("score_match_p_value", 1)
    st.metric("Spearman Correlation", f"{corr:.4f}")
    st.metric("P-value", f"{p_val:.4f}")
    if p_val < 0.05:
        st.success("Statistically significant correlation detected.")
    else:
        st.info("No significant correlation — consistent with lottery randomness.")

    # Interpretation
    st.subheader("Interpretation")
    st.markdown(summary.get("interpretation", ""))

    # Disclaimer
    st.divider()
    st.caption(result.get("disclaimer", ""))
