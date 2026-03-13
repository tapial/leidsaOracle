"""Dashboard page — draw stats, latest results, quick actions."""

from __future__ import annotations

import httpx
import streamlit as st


def render(api_base: str):
    st.title("Dashboard")

    # Health check
    try:
        resp = httpx.get(f"{api_base}/health", timeout=5)
        health = resp.json()
        col1, col2, col3 = st.columns(3)
        col1.metric("Status", health.get("status", "unknown"))
        col2.metric("Total Draws", health.get("draw_count", 0))
        col3.metric("Database", "Connected" if health.get("db_ok") else "Error")
    except Exception as e:
        st.error(f"Cannot reach API at {api_base}: {e}")
        return

    st.divider()

    # Latest draws
    st.subheader("Latest Draws")
    game_type = st.selectbox("Game Type", ["loto", "loto_mas", "loto_pool"])

    try:
        resp = httpx.get(f"{api_base}/draws", params={"game_type": game_type, "limit": 10}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            draws = data.get("draws", [])
            if draws:
                for draw in draws:
                    nums = ", ".join(str(n) for n in draw["numbers"])
                    bonus = f" + bonus: {draw['bonus_number']}" if draw.get("bonus_number") else ""
                    st.text(f"{draw['draw_date']}  →  [{nums}]{bonus}  ({draw.get('source', '')})")
            else:
                st.info("No draws found. Try scraping or importing data first.")
        else:
            st.warning(f"API returned status {resp.status_code}")
    except Exception as e:
        st.error(f"Failed to fetch draws: {e}")

    st.divider()

    # Quick actions
    st.subheader("Quick Actions")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Scrape Latest Results"):
            try:
                resp = httpx.post(
                    f"{api_base}/import/scrape/latest",
                    params={"game_type": game_type},
                    timeout=60,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    st.success(
                        f"Scraped! Found: {result.get('draws_found', 0)}, "
                        f"Imported: {result.get('draws_imported', 0)}, "
                        f"Skipped: {result.get('draws_skipped', 0)}"
                    )
                else:
                    st.error(f"Scraper failed: {resp.text}")
            except Exception as e:
                st.error(f"Scraper error: {e}")

    with col2:
        uploaded = st.file_uploader("Upload Excel", type=["xlsx", "xls"])
        if uploaded:
            try:
                files = {"file": (uploaded.name, uploaded.getvalue())}
                resp = httpx.post(
                    f"{api_base}/import/excel",
                    files=files,
                    data={"game_type": game_type},
                    timeout=60,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    st.success(f"Imported {result.get('draws_imported', 0)} draws!")
                else:
                    st.error(f"Import failed: {resp.text}")
            except Exception as e:
                st.error(f"Import error: {e}")

    with col3:
        if st.button("Generate Combinations"):
            st.info("Select **Generator** in the sidebar to generate combinations.")

    # Disclaimer
    st.divider()
    st.caption(
        "DISCLAIMER: Lottery draws are independent random events. "
        "Past patterns do NOT predict future outcomes. This is a research tool only."
    )
