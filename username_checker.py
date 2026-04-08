

import os
import asyncio
import itertools
import socket
import re
import discord
from discord import app_commands
import aiohttp
import whois
import dns.resolver
import phonenumbers
from phonenumbers import geocoder, carrier, timezone

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
LETTERS = "abcdefghijklmnopqrstuvwxyz"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def truncate(text: str, limit: int = 1024) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# on_ready
# ---------------------------------------------------------------------------

@client.event
async def on_ready():
    for guild in client.guilds:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        print(f"Synced commands to guild: {guild.name} ({guild.id})")
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    print("Slash commands synced. Bot is ready.")


# ---------------------------------------------------------------------------
# /check — bulk 3-letter username availability
# ---------------------------------------------------------------------------

async def _check_discord_username(session: aiohttp.ClientSession, username: str) -> bool:
    url = "https://discord.com/api/v9/unique-username/validate"
    try:
        async with session.get(url, params={"username": username},
                               timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("taken") is False
    except Exception:
        pass
    return False


async def _check_tiktok_username(session: aiohttp.ClientSession, username: str) -> bool:
    url = f"https://www.tiktok.com/@{username}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        async with session.get(url, headers=headers, allow_redirects=True,
                               timeout=aiohttp.ClientTimeout(total=10)) as resp:
            text = await resp.text()
            return "User not found" in text or resp.status == 404
    except Exception:
        pass
    return False


@tree.command(name="check", description="Check all 3-letter username combos on Discord and/or TikTok")
@app_commands.describe(platform="Platform to check: both (default), discord, or tiktok")
async def check_usernames(interaction: discord.Interaction, platform: str = "both"):
    platform = platform.lower()
    if platform not in ("both", "discord", "tiktok"):
        await interaction.response.send_message("Use `both`, `discord`, or `tiktok`.", ephemeral=True)
        return

    total = 26 ** 3
    await interaction.response.send_message(
        f"Checking **{total}** 3-letter combinations on **{platform}**. "
        "Updates every 500 checks."
    )

    available = []
    checked = 0
    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        for combo in itertools.product(LETTERS, repeat=3):
            username = "".join(combo)
            checked += 1
            d_ok, t_ok = True, True
            if platform in ("both", "discord"):
                d_ok = await _check_discord_username(session, username)
                await asyncio.sleep(0.3)
            if platform in ("both", "tiktok"):
                t_ok = await _check_tiktok_username(session, username)
                await asyncio.sleep(0.2)
            if d_ok and t_ok:
                available.append(username)
            if checked % 500 == 0:
                pct = checked / total * 100
                await interaction.followup.send(
                    f"**{checked}/{total}** ({pct:.1f}%) — **{len(available)}** available so far."
                )

    if available:
        await interaction.followup.send(f"Done! **{len(available)}** available on **{platform}**:")
        for chunk in [available[i:i+50] for i in range(0, len(available), 50)]:
            await interaction.followup.send("```\n" + ", ".join(chunk) + "\n```")
    else:
        await interaction.followup.send(f"No available 3-letter usernames found on **{platform}**.")


# ---------------------------------------------------------------------------
# /quickcheck — single username check
# ---------------------------------------------------------------------------

@tree.command(name="quickcheck", description="Check a specific username on Discord and TikTok")
@app_commands.describe(username="Username to check (e.g. abc)")
async def quick_check(interaction: discord.Interaction, username: str):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        d = await _check_discord_username(session, username)
        t = await _check_tiktok_username(session, username)
    embed = discord.Embed(title=f"Username check: {username}", color=0x5865F2)
    embed.add_field(name="Discord", value="✅ Available" if d else "❌ Taken / Unknown", inline=True)
    embed.add_field(name="TikTok",  value="✅ Available" if t else "❌ Taken / Unknown", inline=True)
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /usersearch — check username across 20+ platforms
# ---------------------------------------------------------------------------

PLATFORMS = {
    "GitHub":       "https://github.com/{}",
    "GitLab":       "https://gitlab.com/{}",
    "Reddit":       "https://www.reddit.com/user/{}",
    "Instagram":    "https://www.instagram.com/{}/",
    "Twitter/X":    "https://twitter.com/{}",
    "TikTok":       "https://www.tiktok.com/@{}",
    "YouTube":      "https://www.youtube.com/@{}",
    "Twitch":       "https://www.twitch.tv/{}",
    "Pinterest":    "https://www.pinterest.com/{}/",
    "Tumblr":       "https://{}.tumblr.com",
    "Medium":       "https://medium.com/@{}",
    "HackerNews":   "https://news.ycombinator.com/user?id={}",
    "Keybase":      "https://keybase.io/{}",
    "Steam":        "https://steamcommunity.com/id/{}",
    "Pastebin":     "https://pastebin.com/u/{}",
    "Replit":       "https://replit.com/@{}",
    "Linktree":     "https://linktr.ee/{}",
    "Cashapp":      "https://cash.app/${}",
    "Venmo":        "https://venmo.com/{}",
    "SoundCloud":   "https://soundcloud.com/{}",
    "Spotify":      "https://open.spotify.com/user/{}",
    "Roblox":       "https://www.roblox.com/user.aspx?username={}",
    "Chess.com":    "https://www.chess.com/member/{}",
    "Duolingo":     "https://www.duolingo.com/profile/{}",
}

NOT_FOUND_STRINGS = [
    "not found", "page not found", "404", "doesn't exist",
    "user not found", "no user", "could not find", "this page isn't available",
    "this account doesn't exist", "sorry, this page isn't available",
]


async def _platform_exists(session: aiohttp.ClientSession, url: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        async with session.get(url, headers=headers, allow_redirects=True,
                               timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 404:
                return False
            if resp.status == 200:
                text = (await resp.text()).lower()
                return not any(s in text for s in NOT_FOUND_STRINGS)
    except Exception:
        pass
    return False


@tree.command(name="usersearch", description="Search a username across 20+ platforms")
@app_commands.describe(username="Username to search for")
async def usersearch(interaction: discord.Interaction, username: str):
    await interaction.response.defer()
    found, not_found = [], []

    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = {
            name: _platform_exists(session, url.format(username))
            for name, url in PLATFORMS.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    for name, result in zip(tasks.keys(), results):
        url = PLATFORMS[name].format(username)
        if isinstance(result, bool) and result:
            found.append(f"[{name}]({url})")
        else:
            not_found.append(name)

    embed = discord.Embed(
        title=f"Username Search: {username}",
        color=0x2ecc71 if found else 0xe74c3c
    )
    embed.add_field(
        name=f"✅ Found ({len(found)})",
        value="\n".join(found) if found else "None",
        inline=False
    )
    embed.add_field(
        name=f"❌ Not Found ({len(not_found)})",
        value=truncate(", ".join(not_found)) if not_found else "None",
        inline=False
    )
    embed.set_footer(text="Results may be approximate — some platforms block bots.")
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /ip — IP geolocation
# ---------------------------------------------------------------------------

@tree.command(name="ip", description="Geolocate an IP address or hostname")
@app_commands.describe(target="IP address or hostname to look up")
async def ip_lookup(interaction: discord.Interaction, target: str):
    await interaction.response.defer()
    try:
        resolved = socket.gethostbyname(target)
    except socket.gaierror:
        await interaction.followup.send(f"Could not resolve `{target}`.")
        return

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"http://ip-api.com/json/{resolved}?fields=status,message,country,"
            "regionName,city,zip,lat,lon,isp,org,as,hosting,proxy,mobile,query",
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            data = await resp.json()

    if data.get("status") != "success":
        await interaction.followup.send(f"Lookup failed: {data.get('message', 'unknown error')}")
        return

    embed = discord.Embed(title=f"IP Lookup: {data['query']}", color=0x3498db)
    if target != resolved:
        embed.description = f"Resolved from `{target}`"
    embed.add_field(name="Country",  value=data.get("country", "N/A"),     inline=True)
    embed.add_field(name="Region",   value=data.get("regionName", "N/A"),  inline=True)
    embed.add_field(name="City",     value=data.get("city", "N/A"),        inline=True)
    embed.add_field(name="ZIP",      value=data.get("zip", "N/A"),         inline=True)
    embed.add_field(name="Lat/Lon",  value=f"{data.get('lat')}, {data.get('lon')}", inline=True)
    embed.add_field(name="ISP",      value=data.get("isp", "N/A"),         inline=True)
    embed.add_field(name="Org",      value=data.get("org", "N/A"),         inline=True)
    embed.add_field(name="AS",       value=data.get("as", "N/A"),          inline=True)
    flags = []
    if data.get("proxy"):   flags.append("Proxy/VPN")
    if data.get("hosting"): flags.append("Hosting/DC")
    if data.get("mobile"):  flags.append("Mobile")
    embed.add_field(name="Flags", value=", ".join(flags) if flags else "None", inline=True)
    embed.set_footer(text="Data from ip-api.com")
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /whois — domain WHOIS
# ---------------------------------------------------------------------------

@tree.command(name="whois", description="WHOIS lookup for a domain")
@app_commands.describe(domain="Domain to look up (e.g. example.com)")
async def whois_lookup(interaction: discord.Interaction, domain: str):
    await interaction.response.defer()
    domain = domain.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
    try:
        w = await asyncio.get_event_loop().run_in_executor(None, whois.whois, domain)
    except Exception as e:
        await interaction.followup.send(f"WHOIS lookup failed: {e}")
        return

    def fmt(val):
        if val is None:
            return "N/A"
        if isinstance(val, list):
            val = [str(v) for v in val]
            return truncate(", ".join(dict.fromkeys(val)), 256)
        return truncate(str(val), 256)

    embed = discord.Embed(title=f"WHOIS: {domain}", color=0x9b59b6)
    embed.add_field(name="Registrar",    value=fmt(w.get("registrar")),                         inline=False)
    embed.add_field(name="Created",      value=fmt(w.get("creation_date")),                     inline=True)
    embed.add_field(name="Updated",      value=fmt(w.get("updated_date")),                      inline=True)
    embed.add_field(name="Expires",      value=fmt(w.get("expiration_date")),                   inline=True)
    embed.add_field(name="Name Servers", value=fmt(w.get("name_servers")),                      inline=False)
    embed.add_field(name="Status",       value=fmt(w.get("status")),                            inline=False)
    embed.add_field(name="Registrant",   value=fmt(w.get("registrant_name") or w.get("org")),  inline=True)
    embed.add_field(name="Country",      value=fmt(w.get("country")),                           inline=True)
    embed.add_field(name="Emails",       value=fmt(w.get("emails")),                            inline=False)
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /dns — DNS records
# ---------------------------------------------------------------------------

RECORD_TYPES = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "PTR"]


@tree.command(name="dns", description="Look up DNS records for a domain")
@app_commands.describe(domain="Domain to query", record_type="Record type (default: ALL)")
async def dns_lookup(interaction: discord.Interaction, domain: str, record_type: str = "ALL"):
    await interaction.response.defer()
    domain = domain.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
    record_type = record_type.upper()
    types_to_check = [record_type] if record_type != "ALL" else RECORD_TYPES

    embed = discord.Embed(title=f"DNS Records: {domain}", color=0xe67e22)
    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 5
    found_any = False

    for rtype in types_to_check:
        try:
            answers = resolver.resolve(domain, rtype)
            records = [r.to_text() for r in answers]
            embed.add_field(name=rtype, value=truncate("\n".join(records), 1024), inline=False)
            found_any = True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.exception.DNSException):
            if record_type != "ALL":
                embed.add_field(name=rtype, value="No records found.", inline=False)

    if not found_any:
        embed.description = "No DNS records found for this domain."
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /headers — HTTP response headers
# ---------------------------------------------------------------------------

@tree.command(name="headers", description="Fetch HTTP response headers for a URL")
@app_commands.describe(url="URL to inspect (e.g. example.com)")
async def headers_lookup(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    url = clean_url(url)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=True,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                status = resp.status
                headers = dict(resp.headers)
                final_url = str(resp.url)
    except Exception as e:
        await interaction.followup.send(f"Request failed: {e}")
        return

    embed = discord.Embed(
        title=f"HTTP Headers: {url}",
        description=f"**Status:** {status}" + (
            f"\n**Redirected to:** {final_url}" if final_url != url else ""
        ),
        color=0x1abc9c
    )

    interesting = [
        "Server", "X-Powered-By", "Content-Type", "Content-Security-Policy",
        "Strict-Transport-Security", "X-Frame-Options", "X-Content-Type-Options",
        "Set-Cookie", "Location", "Cache-Control", "CF-Ray", "Via",
        "X-Forwarded-For", "Access-Control-Allow-Origin",
    ]
    for key in interesting:
        val = headers.get(key) or headers.get(key.lower())
        if val:
            embed.add_field(name=key, value=truncate(val, 256), inline=False)

    other = {k: v for k, v in headers.items()
             if k not in interesting and k.lower() not in [i.lower() for i in interesting]}
    if other:
        embed.add_field(
            name="Other Headers",
            value=truncate("\n".join(f"`{k}`: {v}" for k, v in list(other.items())[:10])),
            inline=False
        )
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /email — email info (MX records + basic validation)
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


@tree.command(name="email", description="Look up info about an email address (MX, validity)")
@app_commands.describe(email="Email address to investigate")
async def email_lookup(interaction: discord.Interaction, email: str):
    await interaction.response.defer()
    valid_format = bool(EMAIL_RE.match(email))
    domain = email.split("@")[-1] if "@" in email else None

    embed = discord.Embed(
        title=f"Email Info: {email}",
        color=0xe74c3c if not valid_format else 0x2ecc71
    )
    embed.add_field(name="Format Valid", value="✅ Yes" if valid_format else "❌ No", inline=True)

    if not valid_format or not domain:
        await interaction.followup.send(embed=embed)
        return

    embed.add_field(name="Domain", value=domain, inline=True)

    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 5

    try:
        mx = resolver.resolve(domain, "MX")
        mx_records = sorted([(r.preference, r.exchange.to_text()) for r in mx])
        embed.add_field(
            name="MX Records (mail servers)",
            value="\n".join(f"`{pref}` {ex}" for pref, ex in mx_records),
            inline=False
        )
        embed.add_field(name="Deliverable", value="✅ Likely", inline=True)
    except Exception:
        embed.add_field(name="MX Records", value="None found", inline=False)
        embed.add_field(name="Deliverable", value="❌ Unlikely (no MX)", inline=True)

    try:
        txt = resolver.resolve(domain, "TXT")
        spf = [r.to_text() for r in txt if "v=spf1" in r.to_text()]
        dmarc_txt = []
        try:
            dmarc = resolver.resolve(f"_dmarc.{domain}", "TXT")
            dmarc_txt = [r.to_text() for r in dmarc]
        except Exception:
            pass
        if spf:
            embed.add_field(name="SPF", value=truncate(spf[0], 512), inline=False)
        if dmarc_txt:
            embed.add_field(name="DMARC", value=truncate(dmarc_txt[0], 512), inline=False)
    except Exception:
        pass

    embed.set_footer(text="Note: This does not verify if the mailbox exists — only the domain.")
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /phone — phone number info
# ---------------------------------------------------------------------------

@tree.command(name="phone", description="Look up info about a phone number")
@app_commands.describe(number="Phone number in E.164 format (e.g. +12025550123)")
async def phone_lookup(interaction: discord.Interaction, number: str):
    await interaction.response.defer()
    try:
        parsed = phonenumbers.parse(number)
    except phonenumbers.NumberParseException as e:
        await interaction.followup.send(
            f"Could not parse `{number}`. Use E.164 format, e.g. `+12025550123`.\nError: {e}"
        )
        return

    valid = phonenumbers.is_valid_number(parsed)
    possible = phonenumbers.is_possible_number(parsed)
    region = geocoder.description_for_number(parsed, "en")
    carr = carrier.name_for_number(parsed, "en")
    tz = list(timezone.time_zones_for_number(parsed))
    number_type_map = {
        phonenumbers.PhoneNumberType.MOBILE:               "Mobile",
        phonenumbers.PhoneNumberType.FIXED_LINE:           "Fixed Line",
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fixed/Mobile",
        phonenumbers.PhoneNumberType.TOLL_FREE:            "Toll Free",
        phonenumbers.PhoneNumberType.PREMIUM_RATE:         "Premium Rate",
        phonenumbers.PhoneNumberType.VOIP:                 "VoIP",
        phonenumbers.PhoneNumberType.UNKNOWN:              "Unknown",
    }
    num_type = number_type_map.get(phonenumbers.number_type(parsed), "Unknown")

    embed = discord.Embed(
        title=f"Phone Lookup: {phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)}",
        color=0x3498db if valid else 0xe74c3c
    )
    embed.add_field(name="Valid",       value="✅ Yes" if valid else "❌ No",          inline=True)
    embed.add_field(name="Possible",    value="✅ Yes" if possible else "❌ No",        inline=True)
    embed.add_field(name="Type",        value=num_type,                                inline=True)
    embed.add_field(name="Country",     value=region or "Unknown",                     inline=True)
    embed.add_field(name="Carrier",     value=carr or "Unknown (or landline)",         inline=True)
    embed.add_field(name="Timezone(s)", value=", ".join(tz) if tz else "Unknown",      inline=True)
    embed.add_field(
        name="E.164",
        value=phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
        inline=True
    )
    embed.add_field(
        name="National",
        value=phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL),
        inline=True
    )
    embed.set_footer(text="Carrier info may not reflect ported numbers.")
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /portscan — quick TCP port scan
# ---------------------------------------------------------------------------

COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS", 445: "SMB",
    3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL", 6379: "Redis",
    8080: "HTTP-Alt", 8443: "HTTPS-Alt", 27017: "MongoDB",
}


async def _scan_port(host: str, port: int) -> bool:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=1.5
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


@tree.command(name="portscan", description="Scan common ports on a host (non-intrusive)")
@app_commands.describe(target="IP address or hostname to scan")
async def port_scan(interaction: discord.Interaction, target: str):
    await interaction.response.defer()
    try:
        host = socket.gethostbyname(target)
    except socket.gaierror:
        await interaction.followup.send(f"Could not resolve `{target}`.")
        return

    await interaction.followup.send(f"Scanning **{len(COMMON_PORTS)}** common ports on `{host}`...")

    results = await asyncio.gather(*[_scan_port(host, p) for p in COMMON_PORTS])
    open_ports   = [(port, svc) for (port, svc), ok in zip(COMMON_PORTS.items(), results) if ok]
    closed_ports = [(port, svc) for (port, svc), ok in zip(COMMON_PORTS.items(), results) if not ok]

    embed = discord.Embed(
        title=f"Port Scan: {target}" + (f" ({host})" if host != target else ""),
        color=0xe74c3c if open_ports else 0x2ecc71
    )
    embed.add_field(
        name=f"🟢 Open ({len(open_ports)})",
        value="\n".join(f"`{p}` — {s}" for p, s in open_ports) if open_ports else "None",
        inline=False
    )
    embed.add_field(
        name=f"🔴 Closed/Filtered ({len(closed_ports)})",
        value=truncate(", ".join(f"{p}/{s}" for p, s in closed_ports)),
        inline=False
    )
    embed.set_footer(text="Scans common ports only. Results may vary due to firewalls.")
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /reverseip — find domains sharing an IP
# ---------------------------------------------------------------------------

@tree.command(name="reverseip", description="Find domains hosted on the same IP (via HackerTarget)")
@app_commands.describe(target="IP address or hostname")
async def reverse_ip(interaction: discord.Interaction, target: str):
    await interaction.response.defer()
    try:
        host = socket.gethostbyname(target)
    except socket.gaierror:
        await interaction.followup.send(f"Could not resolve `{target}`.")
        return

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.hackertarget.com/reverseiplookup/?q={host}",
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            text = await resp.text()

    if "error" in text.lower() or "API count exceeded" in text:
        await interaction.followup.send(f"Lookup failed or rate limited: `{text.strip()}`")
        return

    domains = [d.strip() for d in text.strip().splitlines() if d.strip()]
    embed = discord.Embed(
        title=f"Reverse IP: {host}",
        description=f"**{len(domains)}** domain(s) found on this IP.",
        color=0x9b59b6
    )
    if domains:
        embed.add_field(
            name="Domains",
            value=truncate("\n".join(domains[:50])),
            inline=False
        )
        if len(domains) > 50:
            embed.set_footer(text=f"Showing first 50 of {len(domains)} domains.")
    await interaction.followup.send(embed=embed)


# ---------------------------------------------------------------------------
# /help — list all commands
# ---------------------------------------------------------------------------

@tree.command(name="help", description="List all available OSINT commands")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="OSINT Bot — Commands", color=0x5865F2)
    cmds = [
        ("/check [platform]",      "Bulk check all 3-letter usernames on Discord/TikTok"),
        ("/quickcheck <username>", "Check a single username on Discord & TikTok"),
        ("/usersearch <username>", "Search a username across 20+ platforms"),
        ("/ip <target>",           "Geolocate an IP address or hostname"),
        ("/whois <domain>",        "WHOIS lookup for a domain"),
        ("/dns <domain> [type]",   "DNS record lookup (A, MX, TXT, NS, etc.)"),
        ("/headers <url>",         "HTTP response headers for a URL"),
        ("/email <email>",         "Email address info (MX, SPF, DMARC, validity)"),
        ("/phone <number>",        "Phone number info (country, carrier, type)"),
        ("/portscan <target>",     "Scan common TCP ports on a host"),
        ("/reverseip <target>",    "Find domains hosted on the same IP"),
    ]
    for name, desc in cmds:
        embed.add_field(name=name, value=desc, inline=False)
    embed.set_footer(text="For educational and research purposes only.")
    await interaction.response.send_message(embed=embed)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

client.run(TOKEN)
