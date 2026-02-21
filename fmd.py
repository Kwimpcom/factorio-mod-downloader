import requests
import json
import os
import sys
import shutil
import traceback
import hashlib
import platform
import difflib
import time
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor
from packaging import version
from pathlib import Path
from rich.console import Console
from rich.table import Table
from flask import Flask, jsonify, request as flask_request
from flask_cors import CORS
from werkzeug.serving import make_server

IGNORED_MODS = {
    "base",
    "space-age",
    "quality",
    "elevated-rails"
}

MAX_RELEASES_DISPLAYED = 6
MAX_WORDS_PER_LINE = 7

USER_AGENT = "Factorio-Agent"

FALLBACK_MIRRORS = [
    ["https://official-factorio-mirror.re146.dev", 0],
    ["https://mods-storage.re146.dev", 0]
]

cli = Console()

title = r"""
  _____          _             _         __  __           _   ____            _        _
 |  ___|_ _  ___| |_ ___  _ __(_) ___   |  \/  | ___   __| | |  _ \ ___  _ __| |_ __ _| |
 | |_ / _` |/ __| __/ _ \| '__| |/ _ \  | |\/| |/ _ \ / _` | | |_) / _ \| '__| __/ _` | |
 |  _| (_| | (__| || (_) | |  | | (_) | | |  | | (_) | (_| | |  __/ (_) | |  | || (_| | |
 |_|  \__,_|\___|\__\___/|_|  |_|\___/  |_|  |_|\___/ \__,_| |_|   \___/|_|   \__\__,_|_|
"""

factorio_path = ""
data_cache = None
checksums = None
executor = None
flask_app = None
server_thread = None
server = None

def get_data_cache():
    return data_cache.result()

def build_data_cache(force_rebuild=False):
    global data_cache
    if data_cache is None or force_rebuild:
        data_cache = executor.submit(lambda: requests.get("https://mods.factorio.com/api/mods?page_size=max", timeout=30).json())

def get_mod_info(name, detailed=False):
    if not detailed:
        match = [res for res in get_data_cache()["results"] if res["name"] == name]
        if len(match) > 0:
            match = dict(match[0])
            if "latest_release" in match:
                match["releases"] = [match.pop("latest_release")]
            return match

    query = "https://mods.factorio.com/api/mods/" + name.replace(" ", "%20") + ("/full" if detailed else "")
    try:
        response = requests.get(query, timeout=15)
        response.raise_for_status()
        result = json.loads(response.text)
        return result
    except Exception as e:
        return {"message": str(e)}

def is_error_packet(modpacket):
    return modpacket is not None and "message" in modpacket.keys()

def similar(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()

def save_userdata():
    global factorio_path
    data = {
        "path": factorio_path
    }
    with open("userdata.json", "w") as file:
        file.write(json.dumps(data, indent=4))

def check_factorio_path(path):
    return os.path.isdir(path) and ("mods" in os.listdir(path) or "data" in os.listdir(path))

def check_factorio_path_set():
    global factorio_path
    return factorio_path != "" and os.path.isdir(factorio_path)

def check_credentials_set():
    return True

def load_userdata():
    global factorio_path
    if os.path.isfile("userdata.json"):
        try:
            with open("userdata.json") as file:
                data = json.loads(file.read())
            factorio_path = data.get("path", "")
        except:
            cli.print("[red]Error loading userdata.json[/red]")

    if not check_factorio_path_set():
        auto_path = "."
        if platform.system() == 'Darwin':
            auto_path = os.path.join(Path.home(), "Library/Application Support/factorio")
        elif platform.system() == "Linux":
            auto_path = os.path.join(Path.home(), ".factorio")
        elif platform.system() == 'Windows':
            auto_path = os.path.join(Path.home(), "AppData/Roaming/Factorio")
        if check_factorio_path(auto_path):
            factorio_path = auto_path

def set_factorio_path():
    global factorio_path
    path = ""
    while True:
        cli.print("[bold green]Insert Factorio path: [/bold green]", end="")
        path = input().strip()
        if not os.path.isdir(path):
            cli.print("[red]Path does not exist.[/red]")
            continue
        if not check_factorio_path(path):
            cli.print("[bold red]!!! Invalid Factorio path (could not find 'mods' or 'data' folders) !!![/bold red]")
            continue
        break
    factorio_path = path
    save_userdata()
    cli.print("[bold green]Path changed![/bold green]")

def split_word_lines(text, words_per_line=MAX_WORDS_PER_LINE):
    words = text.split(" ")
    splitted = list()
    c = 0
    temp = list()
    for word in words:
        if c == words_per_line:
            splitted.append(" ".join(temp))
            temp = list()
            c = 0
        temp.append(word)
        c+=1
    splitted.append(" ".join(temp))
    return splitted

def display_mod_info(packet, max_releases=MAX_RELEASES_DISPLAYED):
    cli.print(f"[bold green]Name:[/bold green] [bold white]{packet.get('title', packet.get('name'))}[/bold white]")
    cli.print(f"[bold green]Owner:[/bold green] [bold white]{packet.get('owner', 'Unknown')}[/bold white]")
    cli.print(f"[bold green]Downloads:[/bold green] [bold white]{str(packet.get('downloads_count', 0))}[/bold white]")
    cli.print(f"[bold green]ID:[/bold green] [bold white]{packet['name']}[/bold white]")
    cli.print(f"\nDescription: ")
    cli.print(f"\n".join(split_word_lines(packet.get('summary', ''))))
    print()

    releases = packet.get("releases", [])
    releases.reverse()
    if max_releases == -1:
        max_releases = len(releases)

    releases_table = Table(title="[bold green]Releases[/bold green]")
    releases_table.add_column("[green]File name[green]")
    releases_table.add_column("[green]Mod Version[green]")
    releases_table.add_column("[green]Game Version[green]")

    i = 0
    for x in releases:
        if i == max_releases:
            releases_table.add_row("", "", "")
            releases_table.add_row(f"[bold red]{str(len(releases) - i)} more...[/bold red]", "", "")
            break
        
        info = x.get("info_json", {})
        game_ver = info.get("factorio_version", "Unknown")
        releases_table.add_row(x["file_name"], x["version"], game_ver)
        i+=1
    cli.print(releases_table)

def check_dirs():
    os.makedirs("mod_cache", exist_ok=True)

def clear_cache():
    if os.path.isdir("mod_cache"):
        shutil.rmtree("mod_cache")
        check_dirs()

def hash_file(filename):
    h = hashlib.sha1()
    with open(filename,'rb') as file:
        while chunk := file.read(8192):
            h.update(chunk)
    return h.hexdigest()

def build_download_urls(packet, release):
    urls = []
    for i in range(len(FALLBACK_MIRRORS)):
        base = FALLBACK_MIRRORS[i][0].rstrip('/')
        url = f"{base}/{packet['name']}/{release['version']}.zip"
        urls.append((url, i))
    return urls

CHECKSUM_FILE = os.path.join("mod_cache", "checksums.json")

def get_cache_checksums():
    global checksums
    if checksums is None:
        if os.path.isfile(CHECKSUM_FILE):
            try:
                with open(CHECKSUM_FILE) as f:
                    checksums = json.loads(f.read())
            except:
                checksums = dict()
        else:
            checksums = dict()
    return checksums

def save_cache_checksums():
    global checksums
    if checksums is not None:
        with open(CHECKSUM_FILE, "w") as f:
            f.write(json.dumps(checksums, indent=4))

def get_file_hash(file):
    current_checksums = get_cache_checksums()
    if file not in current_checksums:
        current_checksums[file] = hash_file(file)
        save_cache_checksums()
    return current_checksums[file]

def download_mod(packet, ver, filter=None):
    release = next((r for r in packet["releases"] if r["version"] == ver), None)
    if not release:
        raise Exception(f"Version {ver} not found in releases")

    urls = build_download_urls(packet, release)
    output_path = os.path.join("mod_cache", release["file_name"])

    if os.path.isfile(output_path):
        expected_sha1 = release["sha1"]
        if expected_sha1 == get_file_hash(output_path):
            cli.print(f"[bold yellow]Using cached version: {release['file_name']}[/bold yellow]")
            return release

    success = False
    for i, (url, mirror_idx) in enumerate(urls):
        try:
            request = requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=30)
            request.raise_for_status()

            with open(output_path, "wb") as file:
                for chunk in request.iter_content(chunk_size=8192):
                    file.write(chunk)

            if hash_file(output_path) != release["sha1"]:
                cli.print("[red]Hash mismatch, trying next mirror...[/red]")
                os.remove(output_path)
                continue

            get_cache_checksums()[output_path] = release["sha1"]
            save_cache_checksums()
            success = True
            break
        except Exception as e:
            if mirror_idx != -1:
                FALLBACK_MIRRORS[mirror_idx][1] += 1
            if i == len(urls) - 1:
                cli.print(f"[red]Failed to download from all sources. Last error: {e}[/red]")
                raise e
    
    if not success:
        raise Exception("Download failed")
    
    if len(FALLBACK_MIRRORS) > 1:
        FALLBACK_MIRRORS.sort(key=lambda mirror: mirror[1])

    cli.print("[bold green]Success[/bold green]")
    return release

def parse_dep_code(code):
    res = {"required": True, "conflict": False}
    code = code.strip()

    if code.startswith("!"):
        res["conflict"] = True
        res["required"] = False
        code = code[1:].strip()
    elif code.startswith("?"):
        res["required"] = False
        code = code[1:].strip()
    elif code.startswith("(?)"):
        res["required"] = False
        code = code[3:].strip()
    
    name_end = len(code)
    for i, char in enumerate(code):
        if not (char.isalnum() or char in "-_"):
            name_end = i
            break
    
    res["name"] = code[:name_end].strip()
    remainder = code[name_end:].strip()

    if remainder:
        sign = ""
        for char in remainder:
            if char in "<>=":
                sign += char
            else:
                break
        
        ver_str = remainder[len(sign):].strip()
        
        if ver_str:
            try:
                ver = version.parse(ver_str)
                res["filter"] = (lambda v: v > ver) if sign == ">" \
                           else (lambda v: v >= ver) if sign == ">=" \
                           else (lambda v: v < ver )if sign == "<" \
                           else (lambda v: v <= ver) if sign == "<=" \
                           else None
            except:
                pass 

    return res

def download_recursive_mod(mod_name, ver="latest", filter=lambda v: True, visited_set=None, min_delay=.05):
    visited_set = visited_set if visited_set is not None else dict()
    
    # Add this check at the beginning
    if mod_name in IGNORED_MODS:
        cli.print(f"[bold yellow]Skipping ignored mod: {mod_name}[/bold yellow]")
        return visited_set
    
    if mod_name in visited_set:
        return visited_set
    visited_set[mod_name] = None

    mod_info = get_mod_info(mod_name, detailed=True)

    if is_error_packet(mod_info):
        cli.print(f"Could not download [bold red]{mod_name}[/bold red]: {mod_info.get('message', 'Unknown Error')}")
        return visited_set

    releases = [r for r in mod_info.get("releases", []) if (not filter) or filter(version.parse(r["version"]))]
    if not releases:
        cli.print(f"[bold red]No matching releases found for {mod_name}[/bold red]")
        return visited_set

    if not ver:
        display_mod_info(mod_info)
        while True:
            cli.print("[bold green]Select release to download (default: latest): [/bold green]", end="")
            inp = input().strip()
            if inp == "":
                ver = releases[-1]["version"]
                break
            if any(r["version"] == inp for r in releases):
                ver = inp
                break
            cli.print("[bold red]!!! Version not found !!![/bold red]")
    elif ver == "latest":
        releases.sort(key=(lambda r: version.parse(r["version"])))
        ver = releases[-1]["version"]

    print(f"Downloading {mod_name} (v{ver})... ", end="", flush=True)
    try:
        target = download_mod(mod_info, ver=ver)
        visited_set[mod_name] = target["file_name"]
    except Exception as e:
        cli.print(f"\n[red]Failed to download {mod_name}: {e}[/red]")
        return visited_set

    time.sleep(min_delay)

    info_json = target.get("info_json", {})
    if "dependencies" in info_json:
        for dep_code in info_json["dependencies"]:
            dep = parse_dep_code(dep_code)
            
            if dep["required"] and not dep["conflict"] and dep["name"] != "base":
                download_recursive_mod(
                    dep["name"],
                    filter=dep.get("filter", None),
                    visited_set=visited_set,
                    min_delay=min_delay
                )

    return visited_set
    
def install_mod(filename):
    global factorio_path
    if not check_factorio_path_set():
        return

    source = os.path.join("mod_cache", filename)
    target = os.path.join(factorio_path, "mods", filename)
    
    os.makedirs(os.path.dirname(target), exist_ok=True)

    cli.print(f"[green]Installing {filename}... [/green]", end='')
    sys.stdout.flush()

    if os.path.isfile(target):
        if hash_file(source) == hash_file(target):
            cli.print("[bright_black]Already installed[/bright_black]")
            return

    try:
        shutil.copy(source, target)
        cli.print("[bold green]Done[/bold green]")
    except Exception as e:
        cli.print(f"[bold red]Failed: {e}[/bold red]")

def install_set(visited_set):
    files_to_install = [val for val in visited_set.values() if val is not None]
    if not files_to_install:
        return
        
    cli.print(f"\n[yellow]Installing {len(files_to_install)} mods...[/yellow]")
    for path in files_to_install:
        install_mod(path)

def search(query, max_similar=5):
    results = get_data_cache().get("results", [])
    matches = [(res, similar(query, res["name"].lower())) for res in results]
    matches.sort(key=lambda p: p[1], reverse=True)
    return matches[:max_similar]

def extract_mod_name_from_url(url):
    if "mods.factorio.com" in url:
        parts = url.rstrip("/").split("/")
        if "mod" in parts:
            try:
                idx = parts.index("mod")
                modname = parts[idx + 1]
                modname = modname.split("?")[0]
                return modname
            except IndexError:
                pass
    return None

def ask_mod_name():
    matches = None
    while True:
        cli.print("[bold green]Insert mod name or URL: [/bold green]", end="")
        name = input().strip()
        
        if "http" in name:
            extracted = extract_mod_name_from_url(name)
            if extracted:
                name = extracted
                cli.print(f"[cyan]Mod name: {name}[/cyan]")
            else:
                cli.print("[red]Could not parse URL[/red]")
                continue

        if matches is not None and name.isdigit():
            idx = int(name)
            if 0 <= idx < len(matches):
                return matches[idx][0]

        packet = get_mod_info(name)
        if is_error_packet(packet):
            matches = search(name)
            longest = 0
            if matches:
                longest = max(len(m[0]["name"]) for m in matches)
            
            cli.print("\nExact match not found. Did you mean:")
            for i, (match, confid) in enumerate(matches):
                padding = " " * (longest - len(match['name']) + 2)
                cli.print(f"[bold yellow][{i}] {match['name']}{padding}({int(confid * 100)}%)[/bold yellow]")
            print()
            
            if not matches:
                 cli.print("[red]No similar mods found.[/red]")
            
            continue
        return packet

def setup_flask_server():
    global flask_app, server, server_thread
    
    flask_app = Flask(__name__)
    CORS(flask_app)
        
    @flask_app.route('/api/download/<mod_name>', methods=['GET'])
    def api_download(mod_name):
        try:
            cli.print(f"\n[bold cyan]Browser requested download: {mod_name}[/bold cyan]")
            visited = {}
            download_recursive_mod(mod_name, ver="latest", visited_set=visited)
            if len(visited) > 0:
                if check_factorio_path_set():
                    install_set(visited)
                    return jsonify({
                        "status": "success", 
                        "mod": mod_name, 
                        "installed": True,
                        "files": list(visited.values())
                    }), 200
                else:
                    return jsonify({
                        "status": "success", 
                        "mod": mod_name, 
                        "installed": False,
                        "message": "Downloaded to cache, but Factorio path not set"
                    }), 200
            else:
                return jsonify({"error": "Failed to resolve mod"}), 404

        except Exception as e:
            cli.print(f"[bold red]API Error:[/bold red] {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500
    
    @flask_app.route('/api/status', methods=['GET'])
    def api_status():
        return jsonify({"status": "running", "factorio_path_set": check_factorio_path_set()}), 200
    
    server = make_server('127.0.0.1', 5000, flask_app)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    cli.print("[bold green]API Server started at http://127.0.0.1:5000[/bold green]")

def shutdown_flask_server():
    global server
    if server:
        server.shutdown()
        server = None
        cli.print("[bold yellow]API Server stopped[/bold yellow]")

def help_menu():
    print("\n")
    cli.print("[bold yellow]1)[/bold yellow] Install mod")
    cli.print("[bold yellow]2)[/bold yellow] Download mod")
    cli.print("[bold yellow]3)[/bold yellow] Import/Update from mod-list.json")
    cli.print("[bold yellow]4)[/bold yellow] View mod info")
    cli.print("[bold yellow]5)[/bold yellow] Set Factorio Path")
    cli.print("[bold yellow]6)[/bold yellow] Clear Cache")
    cli.print("[bold yellow]7)[/bold yellow] Toggle Browser API Server")
    cli.print("[bold yellow]0)[/bold yellow] Exit")

def start():
    opt = 0
    while True:
        try:
            cli.print("\n[bold green]-> [/bold green]", end="")
            inp = input().strip()
            if not inp:
                help_menu()
                continue
            opt = int(inp)
            break
        except ValueError:
            help_menu()
        except KeyboardInterrupt:
            sys.exit(0)

    if opt == 0:
        if server: shutdown_flask_server()
        sys.exit(0)

    elif opt in (1, 2):
        if opt == 1 and not check_factorio_path_set():
            cli.print("[bold red]Factorio path missing! Use option 5.[/bold red]")
            return

        try:
            packet = ask_mod_name()
            if packet:
                visited = download_recursive_mod(packet['name'], ver="latest")
                if opt == 1:
                    install_set(visited)
        except KeyboardInterrupt:
            return

    elif opt == 3:
        cli.print("\n[bold green]Path to mod-list.json (default: ./mod-list.json): [/bold green]", end="")
        path = input().strip() or "mod-list.json"
        
        if not os.path.isfile(path):
            cli.print(f"[red]File {path} not found.[/red]")
            return

        with open(path) as f:
            mod_list = json.loads(f.read())
        
        to_install = dict()
        mods = [m["name"] for m in mod_list["mods"] if m.get("enabled", False) and m["name"] != "base"]
        
        cli.print(f"Found {len(mods)} enabled mods.")
        for mod in mods:
            download_recursive_mod(mod, visited_set=to_install)

        if check_factorio_path_set():
            install_set(to_install)
            target_list = os.path.join(factorio_path, "mods", "mod-list.json")
            shutil.copy(path, target_list)
            cli.print("[green]Updated mod-list.json in game folder.[/green]")

    elif opt == 4:
        packet = ask_mod_name()
        if packet:
            display_mod_info(packet)

    elif opt == 5:
        set_factorio_path()

    elif opt == 6:
        clear_cache()
        cli.print("[green]Cache cleared.[/green]")

    elif opt == 7:
        if server is None:
            setup_flask_server()
        else:
            shutdown_flask_server()

def resolve_mod_name(name_input):
    if "http" in name_input:
        extracted = extract_mod_name_from_url(name_input)
        if extracted:
            cli.print(f"[cyan]Mod name: {extracted}[/cyan]")
            return extracted
        else:
            cli.print(f"[red]Could not parse mod URL: {name_input}[/red]")
            sys.exit(1)
    return name_input

if __name__ == "__main__":
    try:
        executor = ThreadPoolExecutor(max_workers=1)
        check_dirs()
        load_userdata()

        parser = argparse.ArgumentParser(description="Factorio Mod Manager")
        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        p_install = subparsers.add_parser("install", help="Download and install a mod including dependencies")
        p_install.add_argument("modname", help="Name or URL of the mod")

        p_download = subparsers.add_parser("download", help="Download a mod to the cache folder")
        p_download.add_argument("modname", help="Name or URL of the mod")

        p_info = subparsers.add_parser("info", help="Show details about a mod")
        p_info.add_argument("modname", help="Name or URL of the mod")

        p_path = subparsers.add_parser("set-path", help="Set the Factorio installation directory")
        p_path.add_argument("path", help="Path to Factorio folder (containing 'mods' or 'data')")

        p_server = subparsers.add_parser("start-server", help="Start the browser API server")

        p_help = subparsers.add_parser("help", help="List all usable commands")

        args = parser.parse_args()

        if args.command is None:
            print(title)
            print("Fetching Mod Portal database...")
            build_data_cache()
            help_menu()
            while True:
                start()

        elif args.command == "help":
            parser.print_help()
            sys.exit(0)

        elif args.command == "set-path":
            path = args.path.strip()
            if os.path.isdir(path) and check_factorio_path(path):
                factorio_path = path
                save_userdata()
                cli.print(f"[bold green]Success: Factorio path set to {path}[/bold green]")
            else:
                cli.print(f"[bold red]Error: Invalid path. Ensure the folder exists and contains 'mods' or 'data'.[/bold red]")
            sys.exit(0)

        elif args.command == "start-server":
            print("Fetching Mod Portal database...")
            build_data_cache()
            setup_flask_server()
            cli.print("[yellow]Press Ctrl+C to stop the server.[/yellow]")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                shutdown_flask_server()
            sys.exit(0)

        elif args.command == "info":
            print("Fetching Mod Portal database...")
            build_data_cache()
            mod_name = resolve_mod_name(args.modname)
            packet = get_mod_info(mod_name)
            
            if is_error_packet(packet):
                cli.print(f"[red]Error finding mod '{mod_name}': {packet.get('message')}[/red]")
            else:
                display_mod_info(packet)
            sys.exit(0)

        elif args.command in ["install", "download"]:
            print("Fetching Mod Portal database...")
            build_data_cache()
            
            mod_name = resolve_mod_name(args.modname)
            packet = get_mod_info(mod_name)

            if is_error_packet(packet):
                cli.print(f"[red]Mod not found: {mod_name}[/red]")
                matches = search(mod_name)
                if matches:
                    cli.print("Did you mean:")
                    for m, c in matches:
                        cli.print(f" - {m['name']} ({int(c*100)}%)")
                sys.exit(1)

            visited = download_recursive_mod(packet['name'], ver="latest")
            
            if args.command == "install":
                if check_factorio_path_set():
                    install_set(visited)
                else:
                    cli.print("[bold red]Cannot install: Factorio path not set.[/bold red]")
                    cli.print("Use 'python manager.py set-path <path>' or run without arguments to set it.")
            else:
                cli.print("[bold green]Downloads complete.[/bold green]")
            
            sys.exit(0)

    except KeyboardInterrupt:
        if server: shutdown_flask_server()
        sys.exit(0)
    except Exception as exc:
        cli.print(f"\n[bold red]Critical Error:[/bold red] {exc}")
        traceback.print_exc()
        if server: shutdown_flask_server()
        sys.exit(1)
