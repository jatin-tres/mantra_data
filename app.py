import streamlit as st
import pandas as pd
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Page Config ---
st.set_page_config(page_title="Mantra Explorer Scraper", layout="wide")

st.title("Mantra Blockchain Transaction Scraper")
st.markdown("""
This app scrapes 'Coin Balance History' from the Mantra Explorer. 
It automatically toggles the timestamp format and categorizes transactions as **Inflow** or **Outflow**.
""")

# --- Input Section ---
wallet_address = st.text_input(
    "Enter Wallet Address", 
    value="0x2BDfe9E28802b663040aC8Bb2563dd40cF3afef5",
    help="Paste the Mantra wallet address here."
)

# --- Selenium Scraper Function ---
def scrape_mantra_data(address):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # CRITICAL FIX FOR CLOUD: Point to system-installed Chromium
    # Streamlit Cloud installs chromium at /usr/bin/chromium or /usr/bin/chromium-browser
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"

    service = None
    # Use system chromedriver if available (standard in Streamlit Cloud via packages.txt)
    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
    else:
        # Fallback for local testing (Mac/Windows)
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        except:
            st.error("Could not find Chromedriver. Please ensure packages.txt is present.")
            return None

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        st.error(f"Failed to start browser: {e}")
        return None

    # 2. Construct URL
    url = f"https://blockscout.mantrascan.io/address/{address}?tab=coin_balance_history"
    
    status_placeholder = st.empty()
    status_placeholder.info(f"Navigating to {url}...")
    
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 20)
        
        # 3. Wait for table
        status_placeholder.info("Waiting for table data...")
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        
        # 4. Toggle Timestamp (Clock Click)
        try:
            status_placeholder.info("Toggling timestamp format...")
            # Look for the SVG icon specifically inside the 'Timestamp' table header
            # We use a broad XPath to find the 'th' with 'Timestamp' and click any clickable element inside it
            toggle_btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//th[contains(., 'Timestamp')]//*[local-name()='svg' or local-name()='button']")
            ))
            driver.execute_script("arguments[0].click();", toggle_btn)
            time.sleep(2) # Allow UI to update
        except TimeoutException:
            st.warning("Timestamp toggle button not found. Using default time format.")

        # 5. Extract Data
        status_placeholder.info("Extracting rows...")
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        
        data = []
        
        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) < 5: continue
            
            # -- Block --
            block = cols[0].text
            
            # -- Txn (Link extraction) --
            try:
                txn_elem = cols[1].find_element(By.TAG_NAME, "a")
                txn_hash = txn_elem.text
                txn_link = txn_elem.get_attribute("href")
            except:
                txn_hash = cols[1].text
                txn_link = ""

            # -- Timestamp --
            timestamp = cols[2].text
            
            # -- Balance --
            balance = cols[3].text
            
            # -- Delta (Inflow/Outflow Logic) --
            delta_cell = cols[4]
            delta_text = delta_cell.text
            
            # Determine Direction based on text (+/-) AND color if possible
            # We check the HTML class for 'success' (green) or 'danger' (red) clues
            cell_html = delta_cell.get_attribute('innerHTML')
            cell_class = delta_cell.get_attribute('class')
            
            direction = "Unknown"
            
            # Priority 1: Check for explicit plus/minus in text
            if "+" in delta_text:
                direction = "Inflow"
            elif "-" in delta_text:
                direction = "Outflow"
            else:
                # Priority 2: Check standard color classes used by blockscout
                # 'text-success' is usually green, 'text-danger' is usually red
                if "success" in cell_html or "green" in cell_html:
                    direction = "Inflow"
                elif "danger" in cell_html or "error" in cell_html or "red" in cell_html:
                    direction = "Outflow"
                else:
                    direction = "Neutral"

            data.append({
                "Block": block,
                "Txn Hash": txn_hash,
                "Txn Link": txn_link,
                "Timestamp": timestamp,
                "Balance OM": balance,
                "Delta": delta_text,
                "Direction": direction
            })
            
        status_placeholder.success(f"Success! Scraped {len(data)} transactions.")
        return pd.DataFrame(data)

    except Exception as e:
        st.error(f"Scraping failed: {e}")
        return None
    finally:
        driver.quit()

# --- Main Execution ---
if st.button("Fetch Transactions"):
    if not wallet_address:
        st.warning("Please enter a wallet address.")
    else:
        with st.spinner("Initializing scraper..."):
            df = scrape_mantra_data(wallet_address)
            
            if df is not None and not df.empty:
                # Metrics
                inflow_c = len(df[df['Direction'] == 'Inflow'])
                outflow_c = len(df[df['Direction'] == 'Outflow'])
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Txns", len(df))
                c2.metric("Inflow (Green)", inflow_c)
                c3.metric("Outflow (Red)", outflow_c)
                
                # Styling
                def highlight_dir(val):
                    if val == 'Inflow': return 'color: green; font-weight: bold'
                    if val == 'Outflow': return 'color: red; font-weight: bold'
                    return ''

                st.dataframe(
                    df.style.map(highlight_dir, subset=['Direction']),
                    column_config={"Txn Link": st.column_config.LinkColumn("Txn Link")},
                    use_container_width=True
                )
                
                # Download
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("Download CSV", csv, "mantra_data.csv", "text/csv")
            else:
                st.warning("No data found.")
