import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- Page Config ---
st.set_page_config(page_title="Mantra Transaction Explorer", layout="wide")

st.title("Mantra Blockchain Transaction Explorer")
st.markdown("""
This app fetches **Coin Balance History** directly from the Mantra Chain API.
It is faster, more reliable, and does not crash.
""")

# --- Input Section ---
wallet_address = st.text_input(
    "Enter Wallet Address", 
    value="", 
    help="Paste the Mantra wallet address here."
)

# --- API Fetch Function ---
def fetch_mantra_data(address):
    # We use the Blockscout v2 API endpoint for coin balance history
    # This matches the data shown in the "Coin Balance History" tab on the website
    api_url = f"https://blockscout.mantrascan.io/api/v2/addresses/{address}/coin-balance-history"
    
    try:
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 404:
            return "Error: Wallet not found or no history available."
        elif response.status_code != 200:
            return f"Error: API returned status code {response.status_code}"
            
        data = response.json()
        
        # The API returns a list of items in the 'items' key
        items = data.get('items', [])
        
        if not items:
            return "No transaction history found for this address."
            
        processed_data = []
        
        for item in items:
            # 1. Block
            block = item.get('block_number')
            
            # 2. Txn Hash & Link
            txn_hash = item.get('transaction_hash')
            txn_link = f"https://blockscout.mantrascan.io/tx/{txn_hash}" if txn_hash else ""
            
            # 3. Timestamp (API gives ISO format or raw timestamp, we format it)
            raw_time = item.get('timestamp')
            try:
                # Convert ISO string to readable date "Jan 8, 2026 1:38 PM"
                dt_obj = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
                timestamp = dt_obj.strftime("%b %d, %Y %I:%M %p")
            except:
                timestamp = raw_time

            # 4. Values (Amount & Balance)
            # The API returns values in 'Wei' (raw integer), so we divide by 10^18 for OM
            try:
                raw_value = float(item.get('value', 0)) / 1e18
                raw_delta = float(item.get('delta', 0)) / 1e18
            except:
                raw_value = 0.0
                raw_delta = 0.0
            
            # 5. Direction Logic
            direction = "Neutral"
            if raw_delta > 0:
                direction = "Inflow"
            elif raw_delta < 0:
                direction = "Outflow"

            processed_data.append({
                "Block": block,
                "Txn Hash": txn_hash,
                "Txn Link": txn_link,
                "Timestamp": timestamp,
                "Direction": direction,
                "Amount": f"{raw_delta:,.8f}", # Formatted with commas
                "Running Balance OM": f"{raw_value:,.8f}"
            })
            
        return pd.DataFrame(processed_data)

    except requests.exceptions.RequestException as e:
        return f"Network Error: {e}"
    except Exception as e:
        return f"Processing Error: {e}"

# --- Main Execution ---
if st.button("Fetch Transactions"):
    if not wallet_address:
        st.warning("Please enter a wallet address.")
    else:
        with st.spinner("Fetching data from Mantra Chain..."):
            result = fetch_mantra_data(wallet_address)
            
            if isinstance(result, str):
                st.error(result)
            elif isinstance(result, pd.DataFrame):
                df = result
                
                # Metrics
                inflow_count = len(df[df['Direction'] == 'Inflow'])
                outflow_count = len(df[df['Direction'] == 'Outflow'])
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Transactions", len(df))
                c2.metric("Inflows", inflow_count)
                c3.metric("Outflows", outflow_count)
                
                # Styling Helper
                def highlight_row(val):
                    if val == 'Inflow':
                        return 'color: #00c853; font-weight: bold' 
                    elif val == 'Outflow':
                        return 'color: #d50000; font-weight: bold'
                    return ''

                # Display Table with requested order
                # Block → Txn Hash → Txn Link → Timestamp → Direction → Amount → Running Balance OM
                st.dataframe(
                    df.style.map(highlight_row, subset=['Direction']),
                    column_config={
                        "Txn Link": st.column_config.LinkColumn("Txn Link"),
                        "Block": st.column_config.NumberColumn("Block", format="%d")
                    },
                    use_container_width=True
                )
                
                # Download Button
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"mantra_txns_{wallet_address[:6]}.csv",
                    mime="text/csv"
                )
