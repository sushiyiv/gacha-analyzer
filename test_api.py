"""Test the Wuthering Waves gacha API"""
import requests
import json
import sqlite3
import os
from urllib.parse import parse_qs

API_URL = "https://gmserver-api.aki-game2.com/gacha/record/query"

# Find the DB
db_path = None
for p in [
    os.path.expanduser("~/AppData/Roaming/穷观阵/gacha.db"),
    os.path.expanduser("~/AppData/Local/穷观阵/gacha.db"),
    "C:/Users/30982/AppData/Roaming/穷观阵/gacha.db",
]:
    if os.path.exists(p):
        db_path = p
        break

print(f"DB: {db_path}")
if db_path and os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT pool_type, COUNT(*) as cnt, MIN(time) as min_time, MAX(time) as max_time "
        "FROM gacha_records WHERE game='wutheringwaves' GROUP BY pool_type"
    ).fetchall()
    print("=== Current records ===")
    for r in rows:
        print(f"  {r['pool_type']}: {r['cnt']} records ({r['min_time']} ~ {r['max_time']})")
    conn.close()

# Get URL from game log using pure Python decoder
from fetchers.kuro.log_decoder import extract_gacha_urls_from_log
game_exe = "E:/Program File/Wuthering Waves/Wuthering Waves Game/Wuthering Waves.exe"

url = None
if os.path.exists(helper_path) and os.path.exists(game_exe):
    import subprocess
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(
            [helper_path, "/GetGachaURL", game_exe],
            capture_output=True, text=True, timeout=30, creationflags=flags
        )
        out = r.stdout.strip()
        if out:
            urls = json.loads(out)
            if isinstance(urls, list) and urls:
                url = urls[0].get("gachaLink", "")
                print(f"\nGot URL from helper: {url[:100]}...")
    except Exception as e:
        print(f"Helper failed: {e}")

if not url:
    print("Could not get URL from helper. Please paste a URL manually or run the game.")
    exit(1)

# Parse URL params
if "#" in url:
    h = url.split("#", 1)[1]
    if "?" in h:
        params = {k: v[0] for k, v in parse_qs(h.split("?", 1)[1]).items()}
    else:
        params = {}
else:
    params = {}

player_id = params.get("player_id", "102626268")
server_id = params.get("svr_id", "76402e5b20be2c39f095a152090afddc")
record_id = params.get("record_id", "")
resources_id = params.get("resources_id", "")

print(f"\nParsed params: playerId={player_id}, serverId={server_id}")
print(f"  recordId={record_id}")
print(f"  resources_id={resources_id}")

# Test 1: WITH recordId (current behavior)
print("\n=== Test 1: WITH recordId (current) ===")
for pt in [10]:  # just collab for now
    try:
        resp = requests.post(API_URL, json={
            "playerId": player_id, "serverId": server_id,
            "cardPoolId": resources_id, "cardPoolType": pt,
            "languageCode": "zh-Hans", "recordId": record_id,
        }, headers={"Content-Type": "application/json"}, timeout=15)
        data = resp.json()
        records = data.get("data", [])
        print(f"  type={pt}: code={data.get('code')}, records={len(records)}")
        if records:
            print(f"    first: {records[0].get('name','')} @ {records[0].get('time','')}")
            print(f"    last:  {records[-1].get('name','')} @ {records[-1].get('time','')}")
    except Exception as e:
        print(f"  type={pt}: Error: {e}")

# Test 2: WITHOUT recordId
print("\n=== Test 2: WITHOUT recordId ===")
for pt in [10]:
    try:
        resp = requests.post(API_URL, json={
            "playerId": player_id, "serverId": server_id,
            "cardPoolId": resources_id, "cardPoolType": pt,
            "languageCode": "zh-Hans", "recordId": "",
        }, headers={"Content-Type": "application/json"}, timeout=15)
        data = resp.json()
        records = data.get("data", [])
        print(f"  type={pt}: code={data.get('code')}, records={len(records)}")
        if records:
            print(f"    first: {records[0].get('name','')} @ {records[0].get('time','')}")
            print(f"    last:  {records[-1].get('name','')} @ {records[-1].get('time','')}")
    except Exception as e:
        print(f"  type={pt}: Error: {e}")

# Test 3: WITHOUT recordId and WITHOUT cardPoolId
print("\n=== Test 3: WITHOUT recordId and WITHOUT cardPoolId ===")
for pt in [10]:
    try:
        resp = requests.post(API_URL, json={
            "playerId": player_id, "serverId": server_id,
            "cardPoolId": "", "cardPoolType": pt,
            "languageCode": "zh-Hans", "recordId": "",
        }, headers={"Content-Type": "application/json"}, timeout=15)
        data = resp.json()
        records = data.get("data", [])
        print(f"  type={pt}: code={data.get('code')}, records={len(records)}")
        if records:
            print(f"    first: {records[0].get('name','')} @ {records[0].get('time','')}")
            print(f"    last:  {records[-1].get('name','')} @ {records[-1].get('time','')}")
    except Exception as e:
        print(f"  type={pt}: Error: {e}")

# Test 4: ALL pool types WITHOUT recordId
print("\n=== Test 4: ALL pool types WITHOUT recordId ===")
for pt in [1, 2, 3, 4, 5, 8, 9, 10]:
    try:
        resp = requests.post(API_URL, json={
            "playerId": player_id, "serverId": server_id,
            "cardPoolId": "", "cardPoolType": pt,
            "languageCode": "zh-Hans", "recordId": "",
        }, headers={"Content-Type": "application/json"}, timeout=15)
        data = resp.json()
        records = data.get("data", [])
        names = {1:"character",2:"weapon",3:"std_char",4:"std_wpn",5:"beginner",8:"selector",9:"sel_wpn",10:"collab"}
        print(f"  type={pt} ({names.get(pt,'?')}): code={data.get('code')}, records={len(records)}")
    except Exception as e:
        print(f"  type={pt}: Error: {e}")
