import streamlit as st
import pandas as pd
import time
import os
import re
import gc
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
st.markdown("Scrapes 'Coin Balance History' safely using low-memory mode.")

# --- Input ---
wallet_address = st.text_input("Enter Wallet Address", value="")

# --- Ultra-Low Memory Scraper ---
def scrape_mantra_data(address):
    # 1. SETUP: Aggressive Memory Saving Flags
    options = Options()
    options.add_argument("--headless") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage") # Critical for Docker/Cloud
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--window-size=800,600") # Smaller window = Less RAM
    options.add_argument("--single-process") # Saves RAM (might be slightly unstable but necessary here)
    options.add_argument("--no-zygote") # Disables extra processes
    
    # Binary Location Logic
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
        # 2. LAUNCH BROWSER
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(60)
        
        url = f"https://blockscout.mantrascan.io/address/{address}?tab=coin_balance_history"
        driver.get(url)
        
        wait = WebDriverWait(driver, 15) # Reduced wait time
        
        # 3. QUICK CHECK & TOGGLE
        # We wait for the table. If it takes too long, we bail to save RAM.
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))
        
        try:
            # Try to click the clock icon
            toggle_btn = driver.find_element(By.XPATH, "//th[contains(., 'Timestamp')]//*[local-name()='svg']")
            driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {view: window, bubbles:true, cancelable: true}))", toggle_btn)
            time.sleep(1) 
        except:
            pass # Ignore errors here to keep moving

        # 4. CAPTURE & KILL
        html_content = driver.page_source

    except Exception as e:
        return f"Browser Error: {e}"
        
    finally:
        # CRITICAL: Kill browser and free memory immediately
        if driver:
            driver.quit()
        gc.collect() # Force Python to release RAM

    if not html_content:
        return "Error: Empty page source."

    # 5. PARSE (BeautifulSoup - Fast & Light)
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.select("table tbody tr")
        
        data = []
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            # Parsing Logic
            block = cols[0].get_text(strip=True)
            
            # Txn Link & Hash
            txn_link_elem = cols[1].find("a")
            if txn_link_elem:
                raw_href = txn_link_elem.get('href', '')
                txn_link = f"https://blockscout.mantrascan.io{raw_href}" if raw_href.startswith("/") else raw_href
                txn_hash = txn_link.split("/tx/")[-1] if "/tx/" in txn_link else txn_link_elem.get_text(strip=True)
            else:
                txn_link = ""
                txn_hash = cols[1].get_text(strip=True)

            timestamp = cols[2].get_text(strip=True)
            balance = cols[3].get_text(strip=True)
            raw_amount = cols[4].get_text(strip=True)
            
            # Direction Logic
            clean_amount = re.sub(r'[^\d.-]', '', raw_amount)
            direction = "Neutral"
            try:
                val = float(clean_amount)
                if val < 0: direction = "Outflow"
                elif val > 0: direction = "Inflow"
            except:
                pass

            data.append({
                "Block": block,
                "Txn Hash": txn_hash,
                "Txn Link": txn_link,
                "Timestamp": timestamp,
                "Direction": direction,
                "Amount": raw_amount,
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
            
            if isinstance(result, str):
                st.error(result)
            elif isinstance(result, pd.DataFrame):
                df = result
                if df.empty:
                    st.warning("No transactions found.")
                else:
                    # Metrics
                    inflow = len(df[df['Direction'] == 'Inflow'])
                    outflow = len(df[df['Direction'] == 'Outflow'])
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Txns", len(df))
                    c2.metric("Inflows", inflow)
                    c3.metric("Outflows", outflow)
                    
                    # Style
                    def color_row(val):
                        if val == 'Inflow': return 'color: #00c853; font-weight: bold'
                        if val == 'Outflow': return 'color: #d50000; font-weight: bold'
                        return ''

                    # Requested Column Order
                    final_df = df[[
                        "Block", "Txn Hash", "Txn Link", "Timestamp", 
                        "Direction", "Amount", "Running Balance OM"
                    ]]

                    st.dataframe(
                        final_df.style.map(color_row, subset=['Direction']),
                        column_config={"Txn Link": st.column_config.LinkColumn("Txn Link")},
                        use_container_width=True
                    )
                    
                    # Download
                    csv = final_df.to_csv(index=False).encode('utf-8')
                    st.download_button("Download CSV", csv, f"mantra_{wallet_address[:6]}.csv", "text/csv")
