# Username Availability Checker

This script checks the availability of 3-letter usernames on both Discord and TikTok.

## Features
- Generates all 3-letter combinations (aaa → zzz)
- Checks availability on:
  - Discord (via API request)
  - TikTok (via page response)
- Outputs usernames available on both platforms

## Requirements
- Python 3.8+
- Internet connection

## Installation
1. Clone or download this project
2. Install dependencies:

   pip install -r requirements.txt

## Usage
1. Open the script
2. Replace:
   
   YOUR_DISCORD_BOT_TOKEN

   with your actual Discord bot token

3. Run the script:

   python script.py

## Notes / Limitations
- Discord API endpoint used here is not designed for username availability checking and may not work reliably
- TikTok checks rely on page content and may break if their site changes
- Running all combinations (17,576) may take a long time and could trigger rate limits or temporary blocks

## Recommendations
- Add delays between requests to avoid rate limiting
- Consider using async requests (aiohttp) for speed improvements
- Handle API responses more robustly for production use

## Disclaimer
This script is for educational purposes only. Use responsibly and respect platform rate limits and terms of service.
