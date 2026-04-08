import itertools
import requests

# Function to check if a username is available on Discord
def check_discord_username(username):
    url = f"https://discord.com/api/v9/users/@me"
    headers = {
        "Authorization": "YOUR_DISCORD_BOT_TOKEN"
    }
    params = {
        "username": username
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        return response.status_code == 404
    except requests.RequestException as e:
        print(f"Error checking Discord username '{username}': {e}")
        return False

# Function to check if a username is available on TikTok
def check_tiktok_username(username):
    url = f"https://www.tiktok.com/@{username}"
    try:
        response = requests.get(url)
        return "User not found" in response.text
    except requests.RequestException as e:
        print(f"Error checking TikTok username '{username}': {e}")
        return False

# Generate all combinations of 3-letter usernames
letters = 'abcdefghijklmnopqrstuvwxyz'
combinations = itertools.product(letters, repeat=3)

# List to store available usernames
available_usernames = []

# Check each combination
for combo in combinations:
    username = ''.join(combo)
    discord_available = check_discord_username(username)
    tiktok_available = check_tiktok_username(username)

    if discord_available and tiktok_available:
        available_usernames.append(username)

# Print all available usernames
if available_usernames:
    print("Available usernames on both Discord and TikTok:")
    for username in available_usernames:
        print(username)
else:
    print("No available usernames found on both platforms.")
