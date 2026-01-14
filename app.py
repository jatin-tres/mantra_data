import streamlit as st
import pandas as pd
import time
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Page Config ---
st.set_page_config(page_title="Mantra Explorer Scraper", layout="wide")

st.title("Mantra Blockchain Transaction Scraper")
st.markdown("""
This app scrapes 'Coin Balance History' from the Mantra Explorer. 
It automatically toggles the timestamp format and categorizes transactions based on the Amount (+/-).
""")

# --- Input Section ---
wallet_address = st.text_input(
    "Enter Wallet Address", 
    value="0x2BDfe9E28802b663040aC8Bb2563dd40cF3afef5",
    help="Paste the Mantra wallet address here."
)

# --- Selenium Scraper Function ---
def scrape_mantra_data(address):
    # 1. Setup Chrome Options
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # Auto-detect binary location for Streamlit Cloud vs Local
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"

    # Setup Service
    service = None
    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
    else:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        except:
            st.error("Chromedriver not found. If on Cloud, ensure 'packages.txt' contains 'chromium-driver'.")
            return None

    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        
        # 2. Navigate (Silent)
        url = f"https://blockscout.mantrascan.io/address/{address}?tab=coin_balance_history"
        driver.get(url)
        
        wait = WebDriverWait(driver, 25)

        # 3. Wait for Table (Silent)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))
        
        # 4. Toggle Timestamp (Silent)
        try:
            # Target the SVG specifically inside the 'Timestamp' header
            toggle_btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//th[contains(., 'Timestamp')]//*[local-name()='svg']")
            ))
            # Javascript click is reliable for SVGs
            driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {view: window, bubbles:true, cancelable: true}))", toggle_btn)
            time.sleep(2) # Wait for text update
        except Exception:
            # Fail silently on toggle if it doesn't work (data will still load)
            pass

        # 5. Extract Data
        # Re-fetch rows
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        
        data = []
        
        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            
            # Ensure row has enough columns
            if len(cols) < 5:
                continue

            # -- Col 0: Block --
            block = cols[0].get_attribute("textContent").strip()
            
            # -- Col 1 & 2: Txn Link & FULL HASH --
            try:
                txn_elem = cols[1].find_element(By.TAG_NAME, "a")
                txn_link = txn_elem.get_attribute("href")
                
                # Logic: Extract Hash from Link
                if "/tx/" in txn_link:
                    txn_hash = txn_link.split("/tx/")[-1]
                else:
                    txn_hash = txn_elem.get_attribute("textContent").strip()
            except:
                txn_hash = cols[1].get_attribute("textContent").strip()
                txn_link = ""

            # -- Col 3: Timestamp --
            timestamp = cols[2].get_attribute("textContent").strip()
            
            # -- Col 4: Balance (Now Running Balance OM) --
            balance = cols[3].get_attribute("textContent").strip()
            
            # -- Col 5: Amount (formerly Delta) --
            delta_cell = cols[4]
            raw_delta_text = delta_cell.get_attribute("textContent").strip()
            
            # Clean Amount Logic
            clean_amount_str = re.sub(r'[^\d.-]', '', raw_delta_text)
            
            direction = "Neutral"
            try:
                amount_val = float(clean_amount_str)
                if amount_val < 0:
                    direction = "Outflow"
                elif amount_val > 0:
                    direction = "Inflow"
            except ValueError:
                pass

            data.append({
                "Block": block,
                "Txn Hash": txn_hash,
                "Txn Link": txn_link,
                "Timestamp": timestamp,
                "Running Balance OM": balance,
                "Amount": raw_delta_text,
                "Direction": direction
            })
        
        # Create DataFrame
        df = pd.DataFrame(data)
        if not df.empty:
            # Final Requested Order: 
            # Block → Txn Hash → Txn Link → Timestamp → Direction → Amount → Running Balance OM
            df = df[[
                "Block", 
                "Txn Hash", 
                "Txn Link", 
                "Timestamp", 
                "Direction",
                "Amount", 
                "Running Balance OM"
            ]]
            
        return df

    except Exception as e:
        st.error(f"An error occurred: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# --- Main Execution ---
if st.button("Fetch Transactions"):
    if not wallet_address:
        st.warning("Please enter a wallet address.")
    else:
        # Only showing "Processing..." as requested
        with st.spinner("Processing..."):
            df = scrape_mantra_data(wallet_address)
            
            if df is not None and not df.empty:
                # Summary Metrics
                inflow_count = len(df[df['Direction'] == 'Inflow'])
                outflow_count = len(df[df['Direction'] == 'Outflow'])
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Transactions", len(df))
                col2.metric("Inflows (Green)", inflow_count)
                col3.metric("Outflows (Red)", outflow_count)
                
                # Style Helper
                def highlight_row(val):
                    if val == 'Inflow':
                        return 'color: #00c853; font-weight: bold' 
                    elif val == 'Outflow':
                        return 'color: #d50000; font-weight: bold'
                    return ''

                st.subheader("Transaction Details")
                st.dataframe(
                    df.style.map(highlight_row, subset=['Direction']),
                    column_config={
                        "Txn Link": st.column_config.LinkColumn("Txn Link"),
                        "Txn Hash": "Txn Hash",
                        "Block": "Block",
                        "Timestamp": "Timestamp",
                        "Direction": "Direction",
                        "Amount": "Amount",
                        "Running Balance OM": "Running Balance OM"
                    },
                    use_container_width=True
                )
                
                # Download
                csv_data = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download CSV",
                    data=csv_data,
                    file_name=f"mantra_txns_{wallet_address[:6]}.csv",
                    mime="text/csv"
                )
            else:
                st.error("No data found.")
