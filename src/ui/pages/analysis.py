"""Analysis page — frequency charts, hot/cold, pairs, distributions."""

from __future__ import annotations

import httpx
import pandas as pd
import streamlit as st


def render(api_base: str):
    st.title("Statistical Analysis")
    st.caption("Analyze historical draw patterns across multiple statistical dimensions.")

    game_type = st.selectbox("Game Type", ["loto", "loto_mas", "loto_pool"], key="analysis_game")

    # Run analysis
    col1, col2 = st.columns([1, 3])
    with col1:
        force = st.checkbox("Force refresh")
        if st.button("Run Analysis"):
            with st.spinner("Running analysis..."):
                try:
                    resp = httpx.post(
                        f"{api_base}/analysis/run",
                        json={"game_type": game_type, "force_refresh": force},
                        timeout=120,
                    )
                    if resp.status_code == 200:
                        st.success("Analysis complete!")
                        st.session_state["analysis_data"] = resp.json()
                    else:
                        st.error(f"Analysis failed: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {e}")

    # Display results
    if "analysis_data" not in st.session_state:
        try:
            resp = httpx.get(
                f"{api_base}/analysis/latest",
                params={"game_type": game_type},
                timeout=10,
            )
            if resp.status_code == 200:
                st.session_state["analysis_data"] = resp.json()
        except Exception:
            pass

    data = st.session_state.get("analysis_data")
    if not data:
        st.info("No analysis data available. Run an analysis first.")
        return

    st.subheader(f"Analysis Snapshot — {data.get('draw_count', '?')} draws")

    # Frequency tab
    tab1, tab2, tab3, tab4 = st.tabs(["Frequency", "Hot/Cold", "Pairs", "Distribution"])

    with tab1:
        freq = data.get("frequency", {})
        if freq:
            per_number = freq.get("per_number", {})
            if per_number:
                df = pd.DataFrame([
                    {"Number": int(k), "Count": v.get("count", 0), "Pct": v.get("pct", 0)}
                    for k, v in per_number.items()
                ]).sort_values("Number")
                st.bar_chart(df.set_index("Number")["Count"])
                st.dataframe(df, use_container_width=True)

    with tab2:
        hc = data.get("hot_cold", {})
        if hc:
            per_number = hc.get("per_number", {})
            if per_number:
                df = pd.DataFrame([
                    {"Number": int(k), "Z-Score": v.get("z_score", 0),
                     "Class": v.get("classification", "neutral")}
                    for k, v in per_number.items()
                ]).sort_values("Number")
                st.bar_chart(df.set_index("Number")["Z-Score"])
                st.dataframe(df, use_container_width=True)

    with tab3:
        pairs = data.get("pairs", {})
        if pairs:
            pair_list = pairs.get("pairs", {})
            if pair_list:
                df = pd.DataFrame([
                    {"Pair": k, "Count": v.get("count", 0), "Lift": v.get("lift", 1.0)}
                    for k, v in list(pair_list.items())[:30]
                ]).sort_values("Lift", ascending=False)
                st.dataframe(df, use_container_width=True)

    with tab4:
        dist = data.get("distribution", {})
        if dist:
            st.metric("Sum Mean", f"{dist.get('sum_mean', 0):.1f}")
            st.metric("Sum Std", f"{dist.get('sum_std', 0):.1f}")
            st.metric("Spread Mean", f"{dist.get('spread_mean', 0):.1f}")

    st.divider()
    st.caption(
        "DISCLAIMER: These statistics describe historical patterns. "
        "Lottery draws are random — past frequencies do NOT predict future outcomes."
    )
