import os
import sys
import re
import requests
import shutil
import xml.etree.ElementTree as ET
import statistics
from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen import File
from mutagen.id3 import ID3, TXXX
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from torf import Torrent
import html2text
from bs4 import BeautifulSoup

def main():
    if len(sys.argv) < 2:
        print("Usage: python shovel.py path/to/input.txt")
        sys.exit(1)

    inputtxt_path = sys.argv[1]

    if not os.path.exists(inputtxt_path):
        print("Error: Input file does not exist: " + inputtxt_path)
        sys.exit(1)

    config = parse_input_file(inputtxt_path)

    validate_config(config)

    print("Input file is valid.")


    #Underived metadata retrieval
    announce_url = config.get("announce_url")
    to_anonymize_rss = config.get("anonymize_rss") == 'y'
    to_anonymize_comment = config.get("anonymize_comment") == 'y'
    completed_series = config.get("completed_series") == 'y'
    create_description = config.get("create_description") == 'y'
    create_torrent = config.get("create_torrent") == 'y'
    download_rss = config.get("download_rss") == 'y'
    download_cover = config.get("download_cover") == 'y'
    dry_run = config.get("dry_run") == 'y'
    to_edit_id_tags = config.get("edit_id_tags") == 'y'
    file_input_mode = config.get("file_input_mode")
    file_output_mode = config.get("file_output_mode")
    force_single_episode = config.get("force_single_episode") == 'y'
    ignore_prompts = config.get("ignore_prompts") == 'y'
    input_directory = config.get("input_directory")
    new_title = config.get("title")
    number_reviews = config.get("number_reviews")
    output_directory = config.get("output_directory")
    premium_source = config.get("premium_source")
    to_rename_files = config.get("rename_files") == 'y'
    rss_url = config.get("rss_url")
    stars = config.get("stars")
    website = config.get("website")


    input_path = Path(input_directory)
    output_path = Path(output_directory)
    torrent_source = config.get("torrent_source")

    #provide user a warning if they include media files only semi supported by shovel/ABS
    warning_filetypes = {"m4a", "aac", "wav", "ogg", "opus", "flac"}
    supported_filetypes = {"mp3", "m4a", "ogg", "opus", "flac"}
    warn_filetypes(list_filetypes(input_path, warning_filetypes), ignore_prompts)
    print("Checked media filetypes.")

    #get the data for all supported audio files in input_directory and sort by date descending
    audio_filepaths = get_audio_filepaths(input_path)
    audio_filepaths_data = get_episodes_data(audio_filepaths)
    audio_filepaths_data.sort(key=lambda x: x[1], reverse=True)

    #get derived metadata
    podcast_title = get_podcast_info(config, audio_filepaths_data, "title")
    if file_output_mode != "o":
        completed_series = False
    media_links = get_valid_media_pairs(config)
    author = get_podcast_info(config, audio_filepaths_data, "author")

    if len(audio_filepaths) == 1:
        single_episode_mode = True
    else:
        single_episode_mode = force_single_episode
        if force_single_episode:
            audio_filepaths_data = select_episode(audio_filepaths_data, ignore_prompts)

    #print("Audio filepaths and data 2: ")
    extra_output_folder = transfer_folder(input_path, output_path, file_input_mode)
    if not extra_output_folder:
        extra_output_folder = output_path / "extras"
        extra_output_folder.mkdir(parents=True, exist_ok=True)

    transfer_audio_files(audio_filepaths_data, output_path, file_input_mode)

    #Now that we know which files are being operated on, we can curate all derived metadata

    if to_edit_id_tags:
        edit_id_tags(audio_filepaths_data, new_title, to_anonymize_comment, dry_run)

    if single_episode_mode:
        summary = get_episode_info(audio_filepaths_data[0][0], "summary")
        episode_title = audio_filepaths_data[0][2]
    else:
        summary = get_podcast_info(config, audio_filepaths_data, "summary")
        episode_title = ""

    if summary:
        summary = html_to_bbcode_links_only(summary)

    if to_rename_files:
        rename_files(audio_filepaths_data, podcast_title, dry_run)

    if rss_url and download_rss:
        download_rss_feed(rss_url, podcast_title, extra_output_folder, to_anonymize_rss)
        if download_cover:
            download_cover_art(rss_url, extra_output_folder)

    if not single_episode_mode:
        folders_filepaths_data = organize_folders(audio_filepaths_data, extra_output_folder, output_path, file_output_mode, podcast_title, completed_series, premium_source)
    else:
        _, _, episode_title = audio_filepaths_data[0]
        key_name = output_path / sanitize_filename(make_folder_name(audio_filepaths_data, podcast_title, episode_title, False, premium_source))
        folders_filepaths_data = {key_name: audio_filepaths_data}

    if create_description:
        for name, file_data in folders_filepaths_data.items():
            create_description_outer(file_data, name, output_path, single_episode_mode, podcast_title, website, media_links, author, stars, number_reviews, summary)

    if create_torrent:
        create_torrent_files(output_path, single_episode_mode, announce_url, torrent_source, supported_filetypes)


    print("Exhale!")
    return

def html_to_bbcode_links_only(html_text):
    """
    Convert HTML to BBCode, keeping only links and whitespace-adding elements.
    All other formatting is stripped.
    """
    soup = BeautifulSoup(html_text, 'html.parser')

    # Convert links to BBCode
    for link in soup.find_all('a'):
        href = link.get('href', '')
        text = link.get_text()
        if href:
            bbcode_link = f'[url={href}]{text}[/url]'
            link.replace_with(bbcode_link)

    # Get the text content (this strips all HTML tags)
    text = soup.get_text()

    # Now we need to add back the whitespace from certain tags
    # We'll do this by processing the original HTML again
    soup = BeautifulSoup(html_text, 'html.parser')

    # Replace whitespace-adding tags with placeholders before getting text
    whitespace_tags = {
        'p': '\n\n',
        'br': '\n',
        'div': '\n',
        'h1': '\n\n', 'h2': '\n\n', 'h3': '\n\n', 'h4': '\n\n', 'h5': '\n\n', 'h6': '\n\n',
        'li': '\n',
        'tr': '\n',
        'td': '\t',
        'th': '\t',
    }

    # Convert links first
    for link in soup.find_all('a'):
        href = link.get('href', '')
        text = link.get_text()
        if href:
            bbcode_link = f'[url={href}]{text}[/url]'
            link.replace_with(bbcode_link)

    # Replace whitespace tags with their whitespace equivalents
    for tag_name, whitespace in whitespace_tags.items():
        for tag in soup.find_all(tag_name):
            # For self-closing tags like <br>
            if tag_name in ['br']:
                tag.replace_with(whitespace)
            else:
                # For container tags, add whitespace after the content
                tag.insert_after(whitespace)
                tag.unwrap()  # Remove the tag but keep its contents

    # Get the final text
    result = soup.get_text()

    # Clean up excessive whitespace
    result = '\n'.join(line.strip() for line in result.split('\n'))
    result = result.replace('\n\n\n', '\n\n')  # Max 2 consecutive newlines

    return result.strip()

def anonymize_mp3_comment_tag(mp3_path: Path):
    id3 = ID3(mp3_path)

    for frame in id3.getall("TXXX"):
        if frame.desc.lower() == "comment":
            original_text = frame.text[0] if frame.text else ""
            anonymized = re.sub(
                r'https?://[^ \n\r"]*(token=|user_id=|utm_)[^ \n\r"]*',
                "http://invalid",
                original_text
            )
            frame.text[0] = anonymized

    id3.save(mp3_path)

def create_torrent_files(output_path, single_episode_mode, announce_url, source, audio_exts):
    audio_exts = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus"}

    if single_episode_mode:
        audio_files = [f for f in output_path.iterdir() if f.suffix.lower() in audio_exts and f.is_file()]
        if not audio_files:
            print("No audio file found in single-episode mode.")
            return

        audio_file = audio_files[0]
        torrent_name = audio_file.stem
        torrent_path = output_path / f"{torrent_name}.torrent"

        torrent = Torrent(
            path=audio_file,
            trackers=[announce_url],
            private=True,
            source=source
        )
        torrent.generate()
        torrent.write(torrent_path)
        print(f"Created torrent: {torrent_path.name}")

    else:
        for folder in output_path.iterdir():
            if not folder.is_dir():
                continue

            torrent_name = folder.name
            torrent_path = output_path / f"{torrent_name}.torrent"

            torrent = Torrent(
                path=folder,
                trackers=[announce_url],
                private=True,
                source=source
            )
            torrent.generate()
            torrent.write(torrent_path)
            print(f"Created torrent: {torrent_path.name}")


def find_date_range(audio_filepaths_data):
    valid_dates = []

    for _, date_str, _ in audio_filepaths_data:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "").strip())
            dt = dt.replace(tzinfo=None)  # Make it offset-naive
            valid_dates.append(dt)
        except Exception:
            continue

    if not valid_dates:
        return None, None

    return min(valid_dates).date(), max(valid_dates).date()

#takes in just the single folder audio_filepaths_data
def create_description_outer(audio_filepaths_data, name, output_path, single_episode_mode, podcast_title, website, media_links, author, stars, number_reviews, summary):
    print("Here in create description outer")
    #get filetypes:
    filetypes = list_filetypes_str(audio_filepaths_data)

    #get bitrate
    bitrate = calculate_bitrate(audio_filepaths_data)

    #get num_episodes
    num_episodes = len(audio_filepaths_data)

    #get length
    length = calculate_duration(audio_filepaths_data)

    description_filename = str(name) + ".txt"
    archive_title = format_archive_name(name)

    if single_episode_mode:
        _, _, episode_title = audio_filepaths_data[0]
    else:
        episode_title = ""

    start_date, end_date = find_date_range(audio_filepaths_data)

    create_description_inner(podcast_title, archive_title, description_filename, episode_title, website, media_links, author, stars, number_reviews, summary, filetypes, bitrate, num_episodes, length, start_date, end_date)

def create_description_inner(podcast_title, archive_title, description_filename, episode_title, website, media_links, author, stars, number_reviews, summary, filetypes, bitrate, num_episodes, length, start_date, end_date):
    primary_size = "30"
    secondary_size = "20"
    tertiary_size = "14"

    media_links_string = build_media_links_string(media_links)

    if bitrate:
        bitrate_string = str(round(bitrate)) + " kbps"
    else:
        bitrate_string = "Mixed"

    if length:
        hours = length // 60
        mins = length % 60
        length_string = f"{hours}hr {mins}min" if hours > 0 else f"{mins}min"
    else:
        length_string = "n/a"

    #print("About to open file: ")
    #print(str(description_filename))
    #sys.exit(0)
    #separated out into two long cases for easy editing, at the cost of redundant lines and two points of truth
    print(f"Description Filename is: {description_filename}")

    if episode_title == "":
        with open(description_filename, "w", encoding="utf-8") as f:
            f.write(f"Title: {archive_title}\n\n")
            f.write(f"Description:\n\n")
            f.write(f"[center]\n")
            f.write(f"[b][size={primary_size}][url={website}]{podcast_title}[/url][/size][/b]\n")
            f.write(f"{media_links_string}\n")#media_links
            f.write(f"[b][size={tertiary_size}]By: {author}[/size][/b]\n")
            if stars != "":
                f.write(f"★ {stars} ({number_reviews})\n")
            f.write("\n")
            f.write(f"[i]{summary}[/i]")
            f.write("\n")
            f.write("\n___\n")
            f.write(f"Filetypes(s): [b]{filetypes}[/b] | Bitrate: [b]{bitrate_string}[/b] | Number of Episodes: [b]{num_episodes}[/b]\n")
            f.write(f"Average Episode Length: [b]{length}min[/b] | Start Date: [b]{start_date}[/b] | End Date: [b]{end_date}[/b]\n")
            f.write("[size=10]Assisted by [url=https://github.com/Apprentice57]Shovel[/url][/size]")
            f.write(f"[/center]")
    else:
        print("Yeah in the else statement")
        with open(description_filename, "w", encoding="utf-8") as f:
            f.write(f"Title: {archive_title}\n\n")
            f.write(f"Description:\n\n")
            f.write(f"[center]\n")
            f.write(f"[b][size={secondary_size}]{podcast_title}[/size][/b]\n")
            f.write(f"[b][size={primary_size}][url={website}]{episode_title}[/url][/size][/b]\n")
            f.write(f"{media_links_string}\n")
            f.write(f"[b][size={tertiary_size}]By: {author}[/size][/b]\n")
            if stars != "":
                f.write(f"★ {stars} ({number_reviews})\n")
            f.write("\n")
            f.write(f"[i]{summary}[/i]")
            f.write("\n")
            f.write("\n___\n")
            f.write(f"Filetypes(s): [b]{filetypes}[/b] | Bitrate: [b]{bitrate_string}[/b]\n")
            f.write(f"Episode Length: [b]{length}min[/b] | Date: [b]{start_date}[/b]\n")
            f.write("[size=10]Assisted by [url=https://github.com/Apprentice57]Shovel[/url][/size]")
            f.write(f"[/center]")

#Archive name standards ask a "/" instead of " - " to separate the years from the file formats
#The latter is used for folder naming as "/" is inadvisable in a path.
def format_archive_name(full_path_str):
    archive_name = Path(full_path_str).name

    bracket_index = archive_name.find("[")
    if bracket_index != -1:
        dash_index = archive_name.find(" - ", bracket_index)
        if dash_index != -1:
            archive_name = archive_name[:dash_index] + "/" + archive_name[dash_index + 3:]

    return archive_name

def build_media_links_string(media_links):
    links = [f"[url={url}][img]{thumb}[/img][/url]" for url, thumb in media_links]
    return " ".join(links)

def download_cover_art(rss_url, target_folder):
    try:
        response = requests.get(rss_url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        ns = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}

        image_url = None
        itunes_image = root.find('.//itunes:image', ns)
        if itunes_image is not None:
            image_url = itunes_image.attrib.get('href')
        else:
            url_elem = root.find('.//image/url')
            if url_elem is not None:
                image_url = url_elem.text

        if image_url:
            image_response = requests.get(image_url, timeout=10)
            image_response.raise_for_status()
            cover_path = Path(target_folder) / "cover.jpg"
            with open(cover_path, 'wb') as f:
                f.write(image_response.content)
            print(f"Downloaded cover art to {cover_path}")
        else:
            print("No <itunes:image> or <image><url> tag found in RSS feed.")
    except Exception as e:
        print(f"Failed to download cover art: {e}")

def organize_folders(audio_filepaths_data, extra_output_folder, output_path, file_output_mode, podcast_title, completed_series, premium_source):
    year_to_files = {}

    for file_path, date_str, episode_title in audio_filepaths_data:
        try:
            year = int(date_str[:4])
            year_to_files.setdefault(year, []).append((file_path, date_str, episode_title))
        except (ValueError, TypeError):
            continue

    all_years = sorted(year_to_files.keys())
    folders = {}

    if file_output_mode == 'o':
        folder_name = make_folder_name(audio_filepaths_data, podcast_title, "", completed_series, premium_source)
        folder_path = output_path / sanitize_filename(folder_name)
        folder_path.mkdir(parents=True, exist_ok=True)
        folders[folder_path] = audio_filepaths_data

    elif file_output_mode == 't':
        if not all_years:
            return {}

        latest = all_years[-1]
        rest = all_years[:-1]

        if latest in year_to_files:
            subset = year_to_files[latest]
            folder_name = make_folder_name(subset, podcast_title, "", False, premium_source)
            folder_path = output_path / sanitize_filename(folder_name)
            folder_path.mkdir(parents=True, exist_ok=True)
            folders[folder_path] = subset

        if rest:
            combined_subset = []
            for y in rest:
                combined_subset.extend(year_to_files[y])
            folder_name = make_folder_name(combined_subset, podcast_title, "", False, premium_source)
            folder_path = output_path / sanitize_filename(folder_name)
            folder_path.mkdir(parents=True, exist_ok=True)
            folders[folder_path] = combined_subset

    elif file_output_mode == 'y':
        for y in all_years:
            subset = year_to_files[y]
            folder_name = make_folder_name(subset, podcast_title, "", False, premium_source)
            folder_path = output_path / sanitize_filename(folder_name)
            folder_path.mkdir(parents=True, exist_ok=True)
            folders[folder_path] = subset

    folder_to_data = {}

    for folder, entries in folders.items():
        folder_to_data[folder] = []

        for file_path, date_str, episode_title in entries:
            new_path = folder / file_path.name
            shutil.move(str(file_path), str(new_path))
            folder_to_data[folder].append((new_path, date_str, episode_title))

        if extra_output_folder:
            shutil.copytree(
                extra_output_folder,
                folder / extra_output_folder.name,
                dirs_exist_ok=True,
                copy_function=os.link
            )

    if extra_output_folder and extra_output_folder.exists():
        shutil.rmtree(extra_output_folder)

    return folder_to_data

def make_folder_name(subset, podcast_title, episode_title, completed_series, premium_source):
    years = [int(date[:4]) for _, date, _ in subset if date]
    if not years:
        date_part = "Unknown"
    elif len(set(years)) == 1:
        date_part = str(years[0])
    else:
        date_part = f"{min(years)}-{max(years)}"

    formats = list_filetypes_str(subset)
    bitrate = bitrate_to_str(calculate_bitrate(subset))
    bitrate_str = f"{bitrate}" if bitrate else "unknown"

    combined_str = ""
    if completed_series and premium_source:
        combined_str = f"(Complete - {premium_source}) "
    elif completed_series:
        combined_str = "(Complete) "
    elif premium_source:
        combined_str = f"({premium_source}) "

    #Include episode title and full YYYY-MM-DD format for a single episode archive
    episode_str = ""
    if episode_title:
        episode_str = "- " + episode_title + " "
        date_str = subset[0][1]  # (path, date, title)
        date_part = date_str[:10] if date_str else "Unknown"

    return f"{podcast_title} {episode_str}{combined_str}[{date_part} - {formats}-{bitrate_str}]"

def calculate_duration(audio_filepaths_data):
    durations = []

    for file_path, _, _ in audio_filepaths_data:
        audio = File(file_path)
        if audio and hasattr(audio.info, 'length'):
            durations.append(audio.info.length / 60)  # convert to minutes

    if not durations:
        return None

    return round(statistics.mean(durations))

#if there is a very common bitrate, with over 70% occurrence, return that
#Allow a difference in 10kbps for that 70% occurrence, so that
#a file with say (127kbps) and another with (say) 128kbps count toward the 70%
def calculate_bitrate(audio_filepaths_data):
    bitrates = []

    for file_path, _, _ in audio_filepaths_data:
        audio = File(file_path)
        if not audio or not hasattr(audio.info, 'bitrate'):
            continue
        bitrates.append(audio.info.bitrate // 1000)  # kbps

    if not bitrates:
        return None

    median = statistics.median(bitrates)
    close = [b for b in bitrates if abs(b - median) <= 10]

    if len(close) / len(bitrates) >= 0.7:
        return int(median)
    return None

def bitrate_to_str(bitrate):
    if bitrate:
        return str(bitrate) + "kbps"
    else:
        return "Mixed"

def included_years(audio_filepaths_data):
    years = set()

    for _, date_str, _ in audio_filepaths_data:
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "").strip())
                years.add(dt.year)
            except ValueError:
                pass  # skip malformed dates

    return sorted(years)

#def organize_folders(audio_filepaths_data, extra_output_folder, output_path):

def download_rss_feed(rss_url, podcast_title, output_path, anonymize):
    try:
        response = requests.get(rss_url, timeout=10)
        response.raise_for_status()

        filename = sanitize_filename(podcast_title) + ".rss"
        rss_path = output_path / filename

        with open(rss_path, 'wb') as f:
            f.write(response.content)
        print("Saved RSS feed to: " + str(rss_path))

        if anonymize:
            print("Anonymizing RSS feed...")
            anonymize_rss_file(rss_path)

    except Exception as e:
        print("Error: Failed to download RSS feed: " + rss_url)
        print("       Exception: " + str(e))

def anonymize_rss_file(path):
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        counter = 1

        for tag in root.iter():
            for attr in tag.attrib:
                val = tag.attrib[attr]
                if 'url' in attr.lower() or 'href' in attr.lower() or 'token=' in val or 'auth=' in val or 'session=' in val:
                    ext = os.path.splitext(urlparse(val).path)[1]
                    tag.attrib[attr] = f"http://invalid/{counter}{ext}"
                    counter += 1

            if tag.text:
                # Replace entire value if it's a full tag like link/guid/etc
                if any(s in tag.tag.lower() for s in ['link', 'url', 'guid']):
                    ext = os.path.splitext(urlparse(tag.text).path)[1]
                    tag.text = f"http://invalid/{counter}{ext}"
                    counter += 1
                else:
                    # Replace matching embedded URLs
                    def replace_url(match):
                        nonlocal counter
                        url = match.group(0)
                        if any(x in url for x in ['token=', 'auth=', 'session=']):
                            ext = os.path.splitext(urlparse(url).path)[1]
                            replacement = f"http://invalid/{counter}{ext}"
                            counter += 1
                            return replacement
                        return url

                    tag.text = re.sub(r'https?://\S+', replace_url, tag.text)

        tree.write(path, encoding='utf-8', xml_declaration=True)
        print(f"Anonymized RSS feed saved to {path}")
    except Exception as e:
        print(f"Failed to anonymize RSS feed: {e}")

def rename_files(audio_filepaths_data, podcast_title, dry_run):
    print("**Renaming files: **")

    for i, (file_path, date, episode_title) in enumerate(audio_filepaths_data):
        ext = file_path.suffix.lower()
        new_name = str(podcast_title) + " - " + str(truncate_date(date)) + " - " + str(episode_title) + str(ext)
        new_name = sanitize_filename(new_name)
        new_path = file_path.parent / new_name

        if not dry_run:
            file_path.rename(new_path)
            audio_filepaths_data[i] = (new_path, date, episode_title)
            renaming_verb = "Renamed"
        else:
            renaming_verb = "Would rename"

        print("  --" + renaming_verb + " '" + file_path.name + " -> '" + new_name + "'")

    return audio_filepaths_data


def truncate_date(date_str):
    date_str = date_str.strip()
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", ""))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        try:
            dt = parsedate_to_datetime(date_str)
            return dt.strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            return date_str

def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def edit_id_tags(audio_filepaths_data, album_override, anonymize_comment, dry_run):
    print("**Editing id tags of files: **")
    for file_path, date, episode_title in audio_filepaths_data:
        delete_tag_map = {
            ".mp3": "TXXX:releasedate, TXXX:year, Date/TDRC, Year/TYER",
            ".m4a": "©day",
            ".ogg": "date, year"
        }
        if album_override != None:
            delete_tag_map[".mp3"] = delete_tag_map[".mp3"] + ", TXXX:MVNM, Album/TALB, Album Sort/TSOA"
            delete_tag_map[".m4a"] = delete_tag_map[".m4a"] + ", ©alb, soal"
            delete_tag_map[".ogg"] = delete_tag_map[".ogg"] + ", Album, Album Sort"

        create_tag_map_date = {
            ".mp3": "Date/TDRC",
            ".m4a": "©day",
            ".ogg": "date"
        }
        create_tag_map_title = {
            ".mp3": "Album/TALB, Album Sort/TSOA",
            ".m4a": "©alb, soal",
            ".ogg": "Album, Album Sort"
        }

        ext = file_path.suffix.lower()

        #common tags with vorbis comments
        if ext == ".flac" or ext == ".opus":
            ext = ".ogg"

        # Use the date from the tuple instead of calling get_episode_info
        #normalized_date = normalize_date(date)

        if not dry_run:
            delete_episode_info(file_path, "date")
            set_episode_info(file_path, "date", date)
            if album_override != None:
                delete_episode_info(file_path, "title")
                set_episode_info(file_path, "title", album_override)

            if anonymize_comment:
                anonymize_mp3_comment_tag(file_path)

            deleting_verb = "Deleted"
            setting_verb = "Set"
            anonymize_verb = "Anonymized"
        else:
            deleting_verb = "Would delete"
            setting_verb = "Would set"
            anonymize_verb = "Would Anonymize"

        print("--File: " + str(file_path))  # Use .name to get just the filename
        print("  -> " + deleting_verb + " field(s): " + delete_tag_map[ext] + "")
        print("  -> " + setting_verb + " field(s): " + create_tag_map_date[ext] + " to: " + date)
        if album_override != None:
            print("  -> " + setting_verb + " field(s): " + create_tag_map_title[ext] + " to: " + album_override)
        if anonymize_comment:
            print("  -> " + anonymize_verb + " the TXXX:Comment field to remove links with identification.")
        print("")
    return

#Currently only suports  "date" and "title" for info
def delete_episode_info(file_path, info):
    ext = file_path.suffix.lower()
    info = info.lower()

    easyid3_tag_map = {
        "date": ["date", "year"],
        "title": ["album", "albumsort"],
    }
    id3_tag_map = {
        "date": ["TXXX:releasedate", "TXXX:year"],
        "title": ["TALB", "TSOA", "TXXX:MVNM"],
    }

    mp4_tag_map = {
        "date": ["©day"],
        "title": ["©alb", "soal"],
    }

    vorbis_tag_map = {
        "date": ["date", "year"],
        "title": ["album", "albumsort"],
    }

    if info not in easyid3_tag_map:
        print("Error: Tried to delete unsupported info: " + info + " from file: " + str(file_path))
        return

    if ext == ".mp3":
        easy = EasyID3(file_path)
        for tag in easyid3_tag_map[info]:
            if tag in easy:
                del easy[tag]
        easy.save()

        id3 = ID3(file_path)
        for frame in id3_tag_map[info]:
            id3.delall(frame)
        id3.save()

    elif ext == ".m4a":
        mp4 = MP4(file_path)
        for key in mp4_tag_map[info]:
            if key in mp4:
                del mp4[key]
        mp4.save()

    elif ext in [".flac", ".ogg", ".opus"]:
        audio = File(file_path)
        for tag in vorbis_tag_map[info]:
            if tag in audio:
                del audio[tag]
        audio.save()

def set_episode_info(file_path, info, value):
    ext = os.path.splitext(file_path)[1].lower()
    info = info.lower()

    tag_map = {
        "date": ["date"],
        "title": ["album", "albumsort"]
    }
    tag_map_mp4 = {
        "date": ["©day"],
        "title": ["©alb", "soal"]
    }

    if info not in tag_map:
        print("Error: Tried to delete unsupported info: " + info + " from file: " + str(file_path))
        return

    if ext == ".mp3":
        easy = EasyID3(file_path)
        for tag in tag_map[info]:
            easy[tag] = value
        easy.save()

    elif ext == ".m4a":
        mp4 = MP4(file_path)
        for tag in tag_map_mp4[info]:
            mp4[tag] = [value]
        mp4.save()

    elif ext in [".flac", ".ogg", ".opus"]:
        audio = File(file_path)
        if audio is not None:
            for tag in tag_map[info]:
                audio[tag] = value
            audio.save()

def transfer_audio_files(audio_filepaths_data, output_path, file_input_mode):
    for i, item in enumerate(audio_filepaths_data):
        source_path = item[0]
        dest_path = output_path / source_path.name

        # Transfer based on mode
        if file_input_mode == "m":  # Move
            shutil.move(str(source_path), str(dest_path))
        elif file_input_mode == "c":  # Copy
            shutil.copy2(str(source_path), str(dest_path))
        elif file_input_mode == "h":  # Hardlink
            os.link(str(source_path), str(dest_path))

        # Update the filepath in the original list, preserving other elements
        audio_filepaths_data[i] = (dest_path,) + item[1:]

    return

def transfer_folder(input_path, output_path, file_input_mode):
    """
    Transfer files from the first subfolder to output directory.

    Args:
        input_directory (str): Path to the input directory
        output_directory (str): Path to the output directory
        file_input_mode (str): Transfer mode - "m" (move), "c" (copy), "h" (hardlink)

    Returns:
        str: Path to the new folder under output_directory
    """

    # Get the first subdirectory found
    subdirs = [d for d in input_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not subdirs:
        return None

    first_subdir = subdirs[0]

    # Create the destination path
    dest_path = output_path / first_subdir.name

    # Transfer based on mode
    if file_input_mode == "m":  # Move
        shutil.move(str(first_subdir), str(dest_path))
    elif file_input_mode == "c":  # Copy
        shutil.copytree(str(first_subdir), str(dest_path),
                       ignore=shutil.ignore_patterns('.DS_Store'),
                       dirs_exist_ok=True)
    elif file_input_mode == "h":  # Hardlink
        shutil.copytree(str(first_subdir), str(dest_path),
                       copy_function=os.link,
                       ignore=shutil.ignore_patterns('.DS_Store'),
                       dirs_exist_ok=True)

    return dest_path

#return the constituents of filetypes that occur in directory
def list_filetypes(input_path, filetypes):
    found = set()
    input_path = Path(input_path)  # Convert to Path object
    for file_path in input_path.iterdir():
        if file_path.is_file():
            ext = file_path.suffix.lower().lstrip(".")
            if ext in filetypes:
                found.add(ext)
    return sorted(found)

def list_filetypes_str(audio_filepaths_data):
    extensions = {
        file_path.suffix.lower().lstrip(".").upper()
        for file_path, _, _ in audio_filepaths_data
    }
    return ",".join(sorted(extensions))

def list_filetypes(input_path, filetypes):
    found = set()
    input_path = Path(input_path)  # Convert to Path object
    for file_path in input_path.iterdir():
        if file_path.is_file():
            ext = file_path.suffix.lower().lstrip(".")
            if ext in filetypes:
                found.add(ext)
    return sorted(found)

#return warnings on included filetypes, based on how ABS currently handles them
def warn_filetypes(filetypes, ignore_prompts):
    if 'm4a' in filetypes:
        print("Warning: At least one .m4a file is included. Downloaders like ABS may not tag .m4a properly, and Shovel does not modify/fix most of those missing tags.")
        print("         It is recommended you check that your .m4a files have proper tags before continuing, so that Shovel can rename them properly.")

    if 'aac' in filetypes:
        print("Warning: At least one .aac file is included. AAC files do not have native tags and so are not supported.")
        print("         It is recommended to (non-destructively) remux these files to .m4a and tag them before continuing.")

    if 'wav' in filetypes:
        print("Warning: At least one .wav file is included. .wav files are not supported.")
        print("         To save space and have better tagging support, it is recommended to transcode to FLAC and tag them before continuing.")

    if any(ext in filetypes for ext in ['ogg', 'opus', 'flac']):
        print("Warning: At least one file with vorbis comments ('id tags') (.ogg, .opus, or .flac) is included.")
        print("         Note that downloaders like ABS tag these mostly correctly, but omit detailed release day info which shovel needs in the 'Date' comment.")
        print("         ABS may also omit optional but useful metadata like a summary/description.")
        print("         You are advised to add required/desired information to the vorbis comments Like below before running, if not there already.")
        print("         'Date': YYYY-MM-DDTHH:MM:SSZ")
        print("               example: 2025-06-22T10:00:00Z")
        print("         'Comment': 'Episode Summary goes here'")

    if not ignore_prompts and filetypes:
        while True:
            result = input("Filetype warning given, continue execution? (y/n): ").strip().lower()
            if result in {'n', 'no'}:
                sys.exit(0)
            elif result in {'y', 'yes'}:
                break
    return

def get_valid_media_pairs(media_dict):
    pairs = []
    for key in media_dict:
        if not key.endswith("_thumb"):
            thumb_key = f"{key}_thumb"
            if thumb_key in media_dict:
                pairs.append((media_dict[key], media_dict[thumb_key]))
    return pairs

    #print("\n".join(f"{k}: {v}" for k, v in config.items()))

    #new_config = convert_config(config)

def parse_input_file(filepath):
    config = {}

    with open(filepath, 'r') as f:
        for lineno, line in enumerate(f, 1):
            raw = line.rstrip('\n')
            stripped = raw.strip()

            if not stripped or stripped.startswith('#'):
                continue

            if ':' not in stripped:
                print("[Line " + str(lineno) + "] Warning: Skipping malformed line: " + raw)
                continue

            key, val = [part.strip() for part in stripped.split(':', 1)]

            # Skip entries with no value
            if val == '':
                continue

            config[key] = val

    convert_synonyms(config)
    return config

def convert_synonyms(config):
    for k, v in config.items():
        lower_v = v.lower()
        if k == "file_input_mode":
            if lower_v == "mv" or lower_v == "move":
                v = "m"
            if lower_v == "copy" or lower_v == "cp":
                v = "c"
            if lower_v == "hardlink" or lower_v == "ln":
                v = "h"

        if k == "file_output_mode":
            if lower_v == "one":
                v = "o"
            if lower_v == "two":
                v = "t"
            if lower_v == "yearly":
                v = "y"

        if lower_v == 'y' or lower_v == 'yes':
            v = 'y'
        if lower_v == 'n' or lower_v == 'no':
            v = 'n'

        config[k] = v
    return

def validate_config(config):
    mandatory = ['input_directory', 'output_directory', 'edit_id_tags', 'dry_run', 'create_description', 'create_torrent']

    if config.get("edit_id_tags") == 'y' or config.get("rename_files") == 'y':
        mandatory.append("file_input_mode")

    if config.get("rss_url"):
        mandatory.append("download_rss")
        mandatory.append("download_cover")

        if config.get("download_rss") == 'y':
            mandatory.append("anonymize_rss")

    if config.get("create_description"):
        mandatory.append("website")

    if config.get("create_torrent") == 'y':
        mandatory.append("announce_url")
        mandatory.append("torrent_source")

    if config.get("file_output_mode") == 'o':
        mandatory.append("completed_series")

    for field in mandatory:
        if not config.get(field):
            print("Error: A value must be provided for the '" + field + "' field.")
            sys.exit(1)

    y_n = ['edit_id_tags', 'rename_files', 'dry_run', 'download_rss', 'anonymize_rss', \
        'download_cover', 'create_description', 'create_torrent', 'ignore_prompts', 'force_single_episode', 'completed_series']
    for field in y_n:
        value = config.get(field)
        if value:
            value = value.lower()
            if not (value == 'y' or value == 'n'):
                print("Error: The value for field: '" + field + "' must be 'y' or 'n'.")
                sys.exit(1)

    multiword = ["title", "summary", "premium_source"]
    for k, v in config.items():
        if ' ' in v and k not in multiword:
            print("Error: The value for field: '" + k + "' must only be one word: '" + v + "'.")
            sys.exit(1)

    value = config.get("file_input_mode")
    if value and value not in {'m', 'c', 'h'}:
        print("Error: The value for field: 'file_input_mode' must be 'm', 'c', or 'h': '" + value + "'.")

    value = config.get("file_output_mode")
    if value and value not in {'o', 't', 'y'}:
        print("Error: The value for field: 'file_output_mode' must be 'o', 't', or 'y': '" + value + "'.")

    validate_directories(config.get("input_directory"), config.get("output_directory"), config.get("ignore_prompts"))
    return

def validate_directories(input_directory, output_directory, ignore_prompts):
    for path in [input_directory, output_directory]:
        if not os.path.isdir(path):
            print(f"Error: '{path}' is not a valid directory.")
            sys.exit(1)

    input_path = Path(input_directory)
    output_path = Path(output_directory)

    # Skip hidden subdirectories like .git
    subdirs = [d for d in input_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if len(subdirs) > 1:
        print(f"Error: input_directory '{input_directory}' can only contain up to one subdirectory (excluding hidden subdirectories).")
        sys.exit(1)

    audio_filepaths = get_audio_filepaths(input_path)
    if not audio_filepaths:
        print(f"Error: Could not find any supported audio files in provided input directory: {input_directory}")
        sys.exit(1)

    ignore_prompts_bool = ignore_prompts == 'y'
    relevant_files = [f for f in output_path.iterdir() if f.name != '.DS_Store']
    if relevant_files:
        print(f"Warning: output_directory: {output_directory} is not empty.")
        if not ignore_prompts_bool:
            while True:
                result = input("Do you want to continue execution? Odd errors may occur if filenames/directory names clash. (y/n): ").lower().strip()
                if result in {'n', 'no'}:
                    sys.exit(0)
                elif result in {'y', 'yes'}:
                    break

#TODO: Take in a list of valid filetypes as input
def get_audio_filepaths(input_path):
    files = sorted(input_path.iterdir())
    audio_files = [
        f for f in files
        if f.is_file() and f.suffix.lower() in ('.mp3', '.m4a', '.ogg', '.opus', '.flac')
    ]
    return audio_files

def get_episodes_data(audio_filepaths):
    """Get episode data (filepath, date, title) for each audio file"""
    episodes_data = []
    for f in audio_filepaths:
        date = normalize_date(get_episode_info(f, "date"))
        title = get_episode_info(f, "episode_title")
        episodes_data.append((f, date, title))
    return episodes_data

def select_episode(episodes_with_dates, ignore_input=False):
    # If ignore_input is True, just return the most recent episode
    if ignore_input:
        return [episodes_with_dates[0]]

    page_size = 10
    current_page = 0
    total_episodes = len(episodes_with_dates)

    while True:
        # Calculate pagination bounds
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, total_episodes)

        # Check if we're out of bounds
        if start_idx >= total_episodes:
            print("No more episodes to display.")
            current_page = max(0, current_page - 1)
            continue

        # Display current page of episodes
        print(f"\nShowing episodes {start_idx + 1}-{end_idx} of {total_episodes}:")
        print("-" * 60)

        current_episodes = episodes_with_dates[start_idx:end_idx]
        for i, (filepath, date, title) in enumerate(current_episodes, 1):
            # Truncate date to YYYY-MM-DDTHH:MM format (remove seconds and beyond)
            truncated_date = date[:16] if len(date) > 16 else date
            print(f"{i:2d}. {truncated_date} - {title}")

        # Get user input
        print("\nOptions:")
        print("  Enter 1-10 to select an episode")
        print("  Enter 'n' for next 10 episodes")
        print("  Enter 'p' for previous 10 episodes")

        choice = input("Your choice: ").strip().lower()

        if choice == 'n':
            # Check if there are more episodes to show
            if end_idx < total_episodes:
                current_page += 1
            else:
                print("Already showing the last page of episodes.")
        elif choice == 'p':
            # Check if there are previous episodes to show
            if current_page > 0:
                current_page -= 1
            else:
                print("Already showing the first page of episodes.")
        else:
        # Try to parse as episode selection
            try:
                episode_num = int(choice)
                if 1 <= episode_num <= len(current_episodes):
                    selected_episode = current_episodes[episode_num - 1]  # Return full tuple, not just [0]
                    print(f"Selected: {selected_episode[0]}")  # Print just the path for display
                    return [selected_episode]  # Return the full tuple
                else:
                    print(f"Please enter a number between 1 and {len(current_episodes)}")
            except ValueError:
                print("Invalid input. Please enter a number, 'n', or 'p'")

def normalize_date(date_str):
    date_str = date_str.strip()
    try:
        # Try ISO 8601 parse (will succeed if already in correct format)
        datetime.fromisoformat(date_str)
        return date_str
    except ValueError:
        pass

    try:
        # Try RFC 822 and convert to ISO 8601
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    except (TypeError, ValueError):
        return date_str
#valid options for info
#title, episode_title, author, episode_number, date, summary, genre, season, season_part
def get_episode_info(file_path, info):
    ext = file_path.suffix.lower()
    info = info.lower()

    # Shared tag map for mp3 and vorbis-style formats
    tag_map = {
        "title": "album",
        "episode_title": "title",
        "author": "artist",
        "episode_number": "tracknumber",
        "date": "date",
        "summary": "comment",
        "genre": "genre",
        "season": "discnumber",
        "season_part": "series-part"
    }
    mp4_tag_map = {
        "title": "©alb",
        "episode_title": "©nam",
        "author": "©ART",
        "episode_number": "trkn",
        "date": "©day",
        "summary": "©cmt",
        "genre": "©gen",
        "season": "disk",
        "season_part": "----:com.apple.iTunes:series-part"
    }

    if ext == ".mp3":
        easy = EasyID3(file_path)
        id3 = ID3(file_path)
        if info in tag_map:
            if info in ["summary", "season_part"]:
                for frame in id3.getall("TXXX"):
                    if frame.desc.lower() == tag_map[info]:
                        if frame.text:
                            return str(frame.text[0]).strip()

                if info == "summary":
                    for frame in id3.getall("COMM"):
                        if frame.desc == "" and frame.lang == "eng":
                            if frame.text:
                                return str(frame.text[0]).strip()

            else:
                value = easy.get(tag_map[info], [None])[0]
                if value and str(value).strip():
                    return str(value).strip()

                # Fallback: check TXXX for releasedate if date is missing or empty
                if info == "date":
                    for frame in id3.getall("TXXX"):
                        if frame.desc.lower() == "releasedate":
                            if frame.text and frame.text[0].strip():
                                return str(frame.text[0]).strip()

    elif ext == ".m4a":
        mp4 = MP4(file_path)
        key = mp4_tag_map.get(info)
        if key and key in mp4:
            value = mp4[key]
            if isinstance(value, list) and value:
                value = value[0]
            if isinstance(value, tuple):
                return str(value[0]).strip()
            if isinstance(value, bytes):
                return value.decode('utf-8').strip()
            if value is not None:
                return str(value).strip()

    elif ext in [".flac", ".ogg", ".opus"]:
        audio = File(file_path)
        if audio is not None:
            tag_key = tag_map.get(info)
            if tag_key and tag_key in audio:
                value = audio[tag_key]
                if isinstance(value, list) and value:
                    return str(value[0]).strip()
                return str(value).strip()

    return None

def get_podcast_info(config, audio_filepaths_data, field):
    # 1. From config
    value = config.get(field)
    if value:
        return value

    # 2. From RSS feed
    rss_url = config.get("rss_url")
    if rss_url:
        rss_queries = {
            "title": ["itunes:title", "title"],
            "author": ["itunes:author", "dc:creator", "author"],
            "summary": ["itunes:summary", "description"]
        }
        for tag in rss_queries.get(field, []):
            value = query_rss(rss_url, tag)
            if value:
                return value

    # 3. From ID tags of first audio file in output_directory
    first_file_path = audio_filepaths_data[0][0]
    tag_map = {
        "title": "title",
        "author": "artist",
        "summary": "summary"
    }
    tag_name = tag_map.get(field)
    if tag_name:
        value = get_episode_info(first_file_path, tag_name)
        if value:
            return value
    return None

def query_rss(rss_url, query):
    try:
        response = requests.get(rss_url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        namespaces = {
            'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
            'dc': 'http://purl.org/dc/elements/1.1/'
        }

        channel = root.find("channel")
        if channel is not None:
            element = channel.find(query, namespaces)
            if element is not None and element.text:
                return element.text.strip()

            # fallback for title
            if query == "itunes:title":
                element = channel.find("title")
                if element is not None and element.text:
                    return element.text.strip()

        return None
    except Exception:
        return None


if __name__ == "__main__":
    main()
