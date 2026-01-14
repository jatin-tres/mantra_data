import streamlit as st
import pandas as pd
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException

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
    # 1. Setup Headless Chrome
    options = Options()
    options.add_argument("--headless")  # Run in background (no GUI)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080") # Ensure elements are visible

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        st.error(f"Error setting up Chrome Driver: {e}")
        return None

    # 2. Construct URL
    url = f"https://blockscout.mantrascan.io/address/{address}?tab=coin_balance_history"
    
    status_placeholder = st.empty()
    status_placeholder.info(f"Navigating to {url}...")
    
    try:
        driver.get(url)
        
        # 3. Wait for the table to load
        wait = WebDriverWait(driver, 15)
        
        # We wait for the 'table' tag to ensure content is present
        status_placeholder.info("Waiting for table data to load...")
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        
        # 4. Handle the "Clock" Click (Toggle Time Format)
        # We look for the header containing 'Timestamp' and find the clickable icon/button inside or near it.
        # Note: Selectors can be tricky. We try to find the button specifically in the Timestamp header.
        try:
            status_placeholder.info("Toggling timestamp format (Age -> Date)...")
            
            # This XPath looks for a table header containing 'Timestamp', then finds a button/svg inside it
            # Adjusting strategy to be generic: Find the th with 'Timestamp' and click the button inside it.
            toggle_btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//th[contains(., 'Timestamp')]//button | //th[contains(., 'Timestamp')]//*[local-name()='svg']")
            ))
            
            # Scroll into view just in case
            driver.execute_script("arguments[0].scrollIntoView();", toggle_btn)
            time.sleep(1) # Small pause for stability
            toggle_btn.click()
            
            # Wait a moment for the text to update from "ago" to a date format
            time.sleep(2) 
            
        except TimeoutException:
            st.warning("Could not find the timestamp toggle button. Scraping with default time format.")

        # 5. Extract Table Data
        status_placeholder.info("Extracting data...")
        
        # Locate the tbody rows
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        
        data = []
        
        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            
            if len(cols) < 5:
                continue # Skip empty or malformed rows
            
            # --- Extract specific columns based on user request ---
            
            # Col 1: Block (Text)
            block = cols[0].text
            
            # Col 2: Txn (Hyperlink)
            # Find the anchor tag inside the second column
            try:
                txn_elem = cols[1].find_element(By.TAG_NAME, "a")
                txn_hash = txn_elem.text
                txn_link = txn_elem.get_attribute("href")
            except:
                txn_hash = cols[1].text
                txn_link = "N/A"
            
            # Col 3: Timestamp (Text - now updated to Date format)
            timestamp = cols[2].text
            
            # Col 4: Balance OM (Text)
            balance = cols[3].text
            
            # Col 5: Delta (Text + Logic for Inflow/Outflow)
            delta_text = cols[4].text
            
            # Logic: Check for '+' or '-' in the text or color classes
            # The prompt mentions: Green (Upward/Inflow), Red (Downward/Outflow)
            # Usually these platforms put a '+' sign for inflow.
            
            direction = "Neutral"
            if "+" in delta_text:
                direction = "Inflow"
            elif "-" in delta_text:
                direction = "Outflow"
            
            # Append to list
            data.append({
                "Block": block,
                "Txn Hash": txn_hash,
                "Txn Link": txn_link,
                "Timestamp": timestamp,
                "Balance OM": balance,
                "Delta": delta_text,
                "Direction": direction  # The new requested column
            })
            
        status_placeholder.success("Scraping complete!")
        return pd.DataFrame(data)

    except Exception as e:
        st.error(f"An error occurred during scraping: {e}")
        return None
        
    finally:
        driver.quit()

# --- Main Execution ---
if st.button("Fetch Transactions"):
    if not wallet_address:
        st.warning("Please enter a wallet address.")
    else:
        with st.spinner("Initializing browser and scraping data..."):
            df = scrape_mantra_data(wallet_address)
            
            if df is not None and not df.empty:
                # Display Summary Metrics
                inflow_count = len(df[df['Direction'] == 'Inflow'])
                outflow_count = len(df[df['Direction'] == 'Outflow'])
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Txns Found", len(df))
                col2.metric("Inflows (Green)", inflow_count)
                col3.metric("Outflows (Red)", outflow_count)
                
                # Highlight Inflow/Outflow in the dataframe display
                def color_direction(val):
                    color = 'green' if val == 'Inflow' else 'red' if val == 'Outflow' else 'black'
                    return f'color: {color}; font-weight: bold'

                st.subheader("Transaction Data")
                
                # Apply styling and show links as actual clickable links
                st.dataframe(
                    df.style.map(color_direction, subset=['Direction']),
                    column_config={
                        "Txn Link": st.column_config.LinkColumn("Txn Link")
                    },
                    use_container_width=True
                )
                
                # Download Button
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Data as CSV",
                    data=csv,
                    file_name=f'mantra_txns_{wallet_address[:6]}.csv',
                    mime='text/csv',
                )
            else:
                st.warning("No data found or table was empty.")
