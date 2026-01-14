import streamlit as st
import pandas as pd
import time
import os
import re
from bs4 import BeautifulSoup
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
It captures the data immediately to prevent memory crashes on cloud servers.
""")

# --- Input Section ---
wallet_address = st.text_input(
    "Enter Wallet Address", 
    value="",
    help="Paste the Mantra wallet address here."
)

# --- Hybrid Scraper Function ---
def scrape_mantra_data(address):
    # --- PHASE 1: SELENIUM (Load Page & Get HTML) ---
    options = Options()
    options.add_argument("--headless") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720") # Smaller window saves RAM
    
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"

    service = None
    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
    else:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        except:
            return "Error: Chromedriver not found."

    driver = None
    html_content = None

    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(45)
        
        url = f"https://blockscout.mantrascan.io/address/{address}?tab=coin_balance_history"
        driver.get(url)
        
        wait = WebDriverWait(driver, 20)
        
        # Wait for table
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))
        
        # Click Toggle (Clock)
        try:
            toggle_btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//th[contains(., 'Timestamp')]//*[local-name()='svg']")
            ))
            driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {view: window, bubbles:true, cancelable: true}))", toggle_btn)
            time.sleep(1.5) # Allow DOM to update
        except:
            pass # Continue even if toggle fails

        # CAPTURE HTML AND EXIT IMMEDIATELY
        html_content = driver.page_source

    except Exception as e:
        return f"Browser Error: {e}"
    finally:
        if driver:
            driver.quit() # Critical: Release memory immediately

    if not html_content:
        return "Error: Failed to capture page source."

    # --- PHASE 2: BEAUTIFUL SOUP (Parse Data safely) ---
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.select("table tbody tr")
        
        data = []
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            # 1. Block
            block = cols[0].get_text(strip=True)

            # 2. Txn Hash & Link
            txn_link_elem = cols[1].find("a")
            if txn_link_elem:
                txn_link = "https://blockscout.mantrascan.io" + txn_link_elem['href'] if txn_link_elem['href'].startswith("/") else txn_link_elem['href']
                # Extract hash from link
                if "/tx/" in txn_link:
                    txn_hash = txn_link.split("/tx/")[-1]
                else:
                    txn_hash = txn_link_elem.get_text(strip=True)
            else:
                txn_link = ""
                txn_hash = cols[1].get_text(strip=True)

            # 3. Timestamp
            timestamp = cols[2].get_text(strip=True)

            # 4. Running Balance
            balance = cols[3].get_text(strip=True)

            # 5. Amount & Direction
            delta_cell = cols[4]
            raw_delta_text = delta_cell.get_text(strip=True)
            
            # Logic: Inflow/Outflow based on cleaned number
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
                "Direction": direction,
                "Amount": raw_delta_text,
                "Running Balance OM": balance
            })

        return pd.DataFrame(data)

    except Exception as e:
        return f"Parsing Error: {e}"

# --- Main Execution ---
if st.button("Fetch Transactions"):
    if not wallet_address:
        st.warning("Please enter a wallet address.")
    else:
        with st.spinner("Processing..."):
            result = scrape_mantra_data(wallet_address)
            
            if isinstance(result, str): # If it returned an error message
                st.error(result)
            elif isinstance(result, pd.DataFrame):
                df = result
                if df.empty:
                    st.warning("No transactions found.")
                else:
                    # Metrics
                    inflow_count = len(df[df['Direction'] == 'Inflow'])
                    outflow_count = len(df[df['Direction'] == 'Outflow'])
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total Txns", len(df))
                    c2.metric("Inflows", inflow_count)
                    c3.metric("Outflows", outflow_count)
                    
                    # Formatting
                    def highlight_row(val):
                        if val == 'Inflow': return 'color: #00c853; font-weight: bold'
                        if val == 'Outflow': return 'color: #d50000; font-weight: bold'
                        return ''

                    st.dataframe(
                        df.style.map(highlight_row, subset=['Direction']),
                        column_config={
                            "Txn Link": st.column_config.LinkColumn("Txn Link")
                        },
                        use_container_width=True
                    )
                    
                    # Download
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button("Download CSV", csv, f"mantra_{wallet_address[:6]}.csv", "text/csv")
