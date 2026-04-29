import asyncio
import smtplib
import os
import random
import signal
import time
import schedule
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

TARGET_URL = "https://www.ticketmaster.ca/noah-kahan-the-great-divide-tour-toronto-ontario-06-28-2026/event/10006441FE5BE5AD?currency-locale=en-us&_gl=1*8d9t5i*_ga*MTE4NTIyMzg4Ni4xNzc3NDI5Mzc0*_ga_C1T806G4DF*czE3Nzc0MjkzNzMkbzEkZzEkdDE3Nzc0Mjk0MTckajE2JGwwJGgw*_ga_H1KKSGW33X*czE3Nzc0MjkzNzMkbzEkZzEkdDE3Nzc0Mjk0MTckajE2JGwwJGgw"
SEARCH_TEXT = "Tickets are sold out now."


def send_email(subject: str, body: str, is_html: bool = False) -> bool:
    """
    Send an email notification using Gmail SMTP.
    
    Args:
        subject: Email subject line
        body: Email body content
        is_html: Whether the body is HTML formatted (default: False)
    
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        gmail_email = os.getenv("GMAIL_EMAIL")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        notify_email = os.getenv("NOTIFY_EMAIL")
        
        # Validate credentials are present
        if not all([gmail_email, gmail_password, notify_email]):
            print("ERROR: Missing email credentials in .env file")
            print("Please create .env from .env.example and add your credentials")
            return False
        
        # Create email message
        msg = MIMEMultipart()
        msg["From"] = gmail_email
        msg["To"] = notify_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html" if is_html else "plain"))
        
        # Send via Gmail SMTP
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_email, gmail_password)
            server.send_message(msg)
        
        print(f"✓ Email sent successfully to {notify_email}")
        return True
        
    except smtplib.SMTPAuthenticationError:
        print("ERROR: Gmail authentication failed. Check your credentials in .env")
        return False
    except Exception as e:
        print(f"ERROR: Failed to send email: {e}")
        return False

def create_ticket_available_email() -> tuple[str, str]:
    """
    Create a formatted email for ticket availability notification.
    
    Returns:
        Tuple of (subject, body) for the email
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = "🎟️ Ticket Update: Noah Kahan Tickets Available!"
    body = f"""<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2>Great news! Tickets appear to be available!</h2>
    <p>Tickets may now be available for the Noah Kahan event.</p>
    <p>
        <a href="{TARGET_URL}" style="display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px;">
            View Event and Purchase Tickets
        </a>
    </p>
    <hr>
    <p><strong>Timestamp:</strong> {timestamp}</p>
    <p><em>This is an automated notification from your Ticket Scraper Bot.</em></p>
</body>
</html>"""
    return subject, body

async def check_for_text():
    async with async_playwright() as p:
        # Launch the browser (headless=True by default)
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print(f"Navigating to {TARGET_URL}...")
        try:
            await page.goto(TARGET_URL)
            
            # Wait for the body to be loaded
            await page.wait_for_load_state("networkidle")
            
            # Search for the text
            content = await page.content()
            if SEARCH_TEXT.lower() in content.lower():
                print(f"FAILURE: Found '{SEARCH_TEXT}'")
                return
            else:
                print(f"SUCCESS: Could not find '{SEARCH_TEXT}'")
                # Send email notification on success
                subject, body = create_ticket_available_email()
                send_email(subject, body, is_html=True)
                return
                
        except Exception as e:
            print(f"An error occurred: {e}")
            return False
        finally:
            await browser.close()

def run_check_wrapper():
    """
    Synchronous wrapper to run the async check_for_text() function.
    Handles exceptions and logs errors without stopping the scheduler.
    """
    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running scheduled check...")
        asyncio.run(check_for_text())
    except Exception as e:
        print(f"ERROR: Check failed with exception: {e}")

def schedule_periodic_checks():
    """
    Main scheduler loop that runs check_for_text() periodically with jitter.
    Gracefully handles shutdown via SIGINT/SIGTERM.
    """
    is_checking = False
    stop_requested = False
    
    def signal_handler(signum, frame):
        nonlocal stop_requested
        print("\n[SCHEDULER] Shutdown signal received...")
        stop_requested = True
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    def check_job():
        nonlocal is_checking
        if is_checking:
            print("[SKIP] Previous check still in progress, skipping this interval")
            return
        is_checking = True
        try:
            run_check_wrapper()
        finally:
            is_checking = False
    
    # Run initial check immediately
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scheduler started. Running initial check...")
    check_job()
    
    # Main scheduling loop
    while not stop_requested:
        # Randomize interval: 17-23 minutes for variance around 20 minutes
        interval_minutes = random.randint(17, 23)
        interval_seconds = interval_minutes * 60
        
        next_check_timestamp = datetime.now().timestamp() + interval_seconds
        next_check_time = datetime.fromtimestamp(next_check_timestamp).strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Next check in {interval_minutes} minutes at {next_check_time}")
        
        # Schedule the job using the schedule library
        schedule.clear()
        schedule.every(interval_minutes).minutes.do(check_job)
        
        # Keep checking for pending jobs until the interval elapses or shutdown is requested
        start_time = time.time()
        while time.time() - start_time < interval_seconds and not stop_requested:
            schedule.run_pending()
            time.sleep(0.5)  # Small sleep to stay responsive to signals
    
    print("[SCHEDULER] Gracefully stopped.")

if __name__ == "__main__":
    try:
        schedule_periodic_checks()
    except KeyboardInterrupt:
        print("\n[MAIN] Keyboard interrupt received.")
