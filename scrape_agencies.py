import asyncio
from playwright.async_api import async_playwright
import re
import csv
import argparse
from urllib.parse import urlparse
import database

async def find_contact_info(context, url, log_callback=None):
    """Visit a website and search for an email address and social media links."""
    email = ""
    socials = {"Instagram": "", "Facebook": "", "LinkedIn": ""}
    
    if log_callback:
        await log_callback(f"Scanning website: {url} ...")
        
    # Create a new page for the website visit
    page = await context.new_page()
    try:
        # Use a reasonable timeout so we don't get stuck
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        content = await page.content()
        
        # 1. Look for mailto links first
        mailto_links = await page.locator('a[href^="mailto:"]').all()
        for link in mailto_links:
            try:
                href = await link.get_attribute('href', timeout=2000)
                if href:
                    extracted = href.replace('mailto:', '').split('?')[0].strip()
                    if '@' in extracted:
                        email = extracted
                        break
            except Exception:
                continue
                
        # 2. If no mailto, try regex
        if not email:
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', content)
            
            # Filter common false positives
            bad_matches = ['.png', '.jpg', '.jpeg', '.gif', 'sentry', 'wix', 'example', 'domain.com']
            valid_emails = []
            for e in set(emails):
                if not any(bad in e.lower() for bad in bad_matches):
                    valid_emails.append(e)
            
            if valid_emails:
                email = valid_emails[0]
                
        # 3. Look for social media links
        all_links = await page.locator('a[href]').all()
        for link in all_links:
            try:
                href = await link.get_attribute('href', timeout=1000)
                if not href: continue
                
                href_lower = href.lower()
                if 'instagram.com' in href_lower and not socials['Instagram']:
                    socials['Instagram'] = href
                elif 'facebook.com' in href_lower and not socials['Facebook']:
                    socials['Facebook'] = href
                elif 'linkedin.com' in href_lower and not socials['LinkedIn']:
                    socials['LinkedIn'] = href
            except Exception:
                continue
                
    except Exception as e:
        if log_callback:
            await log_callback(f"[!] Warning checking website {url}")
        print(f"  [!] Error checking website {url}: {e}")
    finally:
        await page.close()
        
    return email, socials

async def scrape_google_maps(location, keyword="MBBS abroad consultant", log_callback=None):
    query = f"{keyword.strip()} in {location}"
    print(f"Searching Google Maps for: '{query}'")
    if log_callback:
        await log_callback(f"Initializing Google Maps engine...")
        await log_callback(f"Searching for: '{query}'")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # We need geolocation or setting locale to India to get better Indian results
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            locale='en-IN',
            geolocation={'longitude': 78.9629, 'latitude': 20.5937},
            permissions=['geolocation']
        )
        page = await context.new_page()
        
        # Create the search URL directly
        search_query = query.replace(' ', '+')
        url = f"https://www.google.com/maps/search/{search_query}"
        
        await page.goto(url)
        
        # Handle "Accept all" cookies prompt if it appears (common in some regions, though less in IN)
        try:
            accept_btn = page.locator('button:has-text("Accept all")')
            if await accept_btn.count() > 0:
                await accept_btn.click()
        except Exception:
            pass
            
        print("Waiting for results to load...")
        if log_callback:
            await log_callback(f"Waiting for results to load...")
            
        try:
            # Wait for the feed container to load
            await page.wait_for_selector('div[role="feed"]', timeout=20000)
        except Exception:
            msg = "Could not find the results feed. They might have returned no results."
            print(msg)
            if log_callback: await log_callback(msg)
            await browser.close()
            return {"results": [], "filename": ""}
            
        print("Scrolling to load more results...")
        if log_callback: await log_callback("Scrolling to load all available results...")
        feed_selector = 'div[role="feed"]'
        
        # Scroll the feed aggressively
        for _ in range(5):
            await page.evaluate(f'''() => {{
                const target = document.querySelector('{feed_selector}');
                if (target) {{
                    target.scrollBy(0, 5000);
                }}
            }}''')
            await page.wait_for_timeout(2000)
        
        # Find all the result containers
        print("Parsing results...")
        links = await page.locator('a[href*="/maps/place/"]').all()
        urls_to_visit = []
        for link in links:
            href = await link.get_attribute('href')
            if href and href not in urls_to_visit:
                urls_to_visit.append(href)
                
        print(f"Found {len(urls_to_visit)} place links. Extracting details (this will take a moment)...")
        if log_callback:
            await log_callback(f"Found {len(urls_to_visit)} agency links! Extracting detailed profiles...")
            
        results = []
        
        # Process each place
        for url in urls_to_visit:
            try:
                # Go to the place page
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_selector('h1', timeout=10000)
                
                name_elem = await page.locator('h1').first.text_content()
                name = name_elem.strip() if name_elem else "Unknown"
                
                phone = ""
                # Attempt to find phone via the tooltip text
                phone_loc = page.locator('[data-tooltip="Copy phone number"]')
                if await phone_loc.count() > 0:
                    phone = (await phone_loc.first.inner_text()).strip()
                
                website = ""
                # Attempt to find website link via tooltip text
                web_loc = page.locator('[data-tooltip="Open website"]')
                if await web_loc.count() > 0:
                    website = await web_loc.first.get_attribute('href')
                else:
                    # Alternative: anchor tags containing the actual external domain text.
                    # Or data-tooltip something else
                    alt_web_loc = page.locator('a[aria-label^="Website:"]')
                    if await alt_web_loc.count() > 0:
                        website = await alt_web_loc.first.get_attribute('href')
                        
                print(f"Scraped -> {name} | Phone: {phone} | Web: {website}")
                if log_callback:
                    await log_callback(f"Extracted: {name}")
                
                email = ""
                socials = {"Instagram": "", "Facebook": "", "LinkedIn": ""}
                
                if website and website.startswith('http'):
                    email, socials = await find_contact_info(context, website, log_callback)
                    if email:
                        print(f"  -> Found Email: {email}")
                        if log_callback: await log_callback(f"  -> Found Email: {email}")
                        
                results.append({
                    "Name": name,
                    "Phone": phone,
                    "Website": website,
                    "Email": email,
                    "Instagram": socials["Instagram"],
                    "Facebook": socials["Facebook"],
                    "LinkedIn": socials["LinkedIn"],
                    "Location": location
                })
                
            except Exception as e:
                print(f"Failed processing detail for {url}: {e}")
                
        await browser.close()
        
        if not results:
            print("No data was successfully scraped.")
            if log_callback: await log_callback("Scraping finished but no valid agencies were found.")
            return {"results": [], "filename": ""}
            
        output_file = f"{location.replace(' ', '_').lower()}_agencies.csv"
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["Name", "Phone", "Website", "Email", "Instagram", "Facebook", "LinkedIn"])
            writer.writeheader()
            writer.writerows(results)
            
        # Save to SQLite database
        try:
            database.save_leads(results)
            if log_callback: await log_callback("Data persistently saved to Database!")
        except Exception as e:
            print(f"Failed storing to db: {e}")
            
        str_msg = f"\nSuccess! Saved {len(results)} agencies to {output_file}"
        print(str_msg)
        if log_callback: await log_callback(str_msg)
        
        return {"results": results, "filename": output_file}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Medical Agencies from Google Maps")
    parser.add_argument("location", help="State or district in India (e.g., 'Kerala' or 'Ernakulam')")
    args = parser.parse_args()
    
    asyncio.run(scrape_google_maps(args.location))
