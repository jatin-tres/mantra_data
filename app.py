import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- Page Config ---
st.set_page_config(page_title="Mantra Transaction Explorer", layout="wide")

st.title("Mantra Blockchain Transaction Explorer")
st.markdown("""
This app fetches **Coin Balance History** directly from the Mantra Chain API.
**Note:** If the API does not provide a specific timestamp, the **Block Number** is shown as the reference.
""")

# --- Input Section ---
wallet_address = st.text_input(
    "Enter Wallet Address", 
    value="", 
    help="Paste the Mantra wallet address here."
)

# --- API Fetch Function ---
def fetch_mantra_data(address):
    # Endpoint for coin balance history
    api_url = f"https://blockscout.mantrascan.io/api/v2/addresses/{address}/coin-balance-history"
    
    try:
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 404:
            return "Error: Wallet not found or no history available."
        elif response.status_code != 200:
            return f"Error: API returned status code {response.status_code}"
            
        data = response.json()
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
            
            # 3. Timestamp Logic (Robust)
            # We try multiple keys that Blockscout sometimes uses
            raw_time = item.get('timestamp') or item.get('block_timestamp') or item.get('time')
            
            if raw_time:
                try:
                    # Try parsing ISO format (e.g., 2026-01-08T13:38:00.000000Z)
                    dt_obj = datetime.fromisoformat(str(raw_time).replace('Z', '+00:00'))
                    timestamp = dt_obj.strftime("%b %d, %Y %I:%M %p")
                except:
                    # If parsing fails, just use the raw string
                    timestamp = str(raw_time)
            else:
                # Fallback: If API returns no time, show Block Number
                timestamp = f"Block #{block}"

            # 4. Values (Amount & Balance)
            # The API returns values in 'Wei', divide by 1e18 for OM
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
                "Amount": raw_delta,           # Keep as number for sorting/styling
                "Running Balance OM": raw_value # Keep as number for sorting/styling
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
                st.dataframe(
                    df.style.map(highlight_row, subset=['Direction'])
                      .format({
                          "Amount": "{:,.8f}", 
                          "Running Balance OM": "{:,.8f}"
                      }),
                    column_config={
                        "Txn Link": st.column_config.LinkColumn("Txn Link"),
                        "Block": st.column_config.NumberColumn("Block", format="%d"),
                        "Timestamp": st.column_config.TextColumn("Timestamp"),
                    },
                    use_container_width=True
                )
                
                # Download Button (Convert numbers to strings for CSV)
                csv_df = df.copy()
                csv = csv_df.to_csv(index=False).encode('utf-8')
                
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"mantra_txns_{wallet_address[:6]}.csv",
                    mime="text/csv"
                )
