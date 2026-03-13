"""Generator page — generate ranked combinations with explanations."""

from __future__ import annotations

import httpx
import streamlit as st


def render(api_base: str):
    st.title("Combination Generator")

    st.warning(
        "DISCLAIMER: Lottery draws are independent random events. "
        "These combinations are based on statistical heuristics, not predictions. "
        "No combination is more or less likely to win than any other."
    )

    game_type = st.selectbox("Game Type", ["loto", "loto_mas", "loto_pool"], key="gen_game")
    count = st.slider("Number of Combinations", 1, 50, 10)

    # Optional constraints
    with st.expander("Advanced Options"):
        must_include_str = st.text_input("Must include numbers (comma-separated)", "")
        must_exclude_str = st.text_input("Must exclude numbers (comma-separated)", "")

    if st.button("Generate Combinations", type="primary"):
        # Build request
        request = {"game_type": game_type, "count": count}
        constraints = {}
        if must_include_str.strip():
            constraints["must_include"] = [int(n.strip()) for n in must_include_str.split(",") if n.strip()]
        if must_exclude_str.strip():
            constraints["must_exclude"] = [int(n.strip()) for n in must_exclude_str.split(",") if n.strip()]
        if constraints:
            request["constraints"] = constraints

        with st.spinner("Generating combinations..."):
            try:
                resp = httpx.post(
                    f"{api_base}/combinations/generate",
                    json=request,
                    timeout=120,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state["gen_result"] = data
                    st.success(f"Generated {len(data.get('combinations', []))} combinations!")
                else:
                    st.error(f"Generation failed: {resp.text}")
            except Exception as e:
                st.error(f"Error: {e}")

    # Display results
    result = st.session_state.get("gen_result")
    if result:
        st.divider()
        st.subheader(f"Results — Batch {result.get('batch_id', '')[:8]}...")
        st.caption(f"Generated at: {result.get('generated_at', '')}")

        for combo in result.get("combinations", []):
            rank = combo.get("rank", "?")
            numbers = combo.get("numbers", [])
            score = combo.get("ensemble_score", 0)
            nums_str = " - ".join(f"**{n}**" for n in numbers)

            with st.expander(f"#{rank}: [{', '.join(str(n) for n in numbers)}] — Score: {score:.3f}"):
                # Feature scores
                fs = combo.get("feature_scores", {})
                if fs:
                    cols = st.columns(5)
                    for i, (key, val) in enumerate(sorted(fs.items())):
                        if key != "rank":
                            cols[i % 5].metric(key.replace("_score", "").title(), f"{val:.3f}")

                # Percentile
                pct = combo.get("percentile")
                if pct:
                    st.progress(pct / 100, text=f"{pct:.0f}th percentile vs random")

                # Explanation
                explanation = combo.get("explanation", "")
                if explanation:
                    st.markdown(explanation)

        # Disclaimer at bottom
        st.divider()
        st.caption(result.get("disclaimer", ""))
