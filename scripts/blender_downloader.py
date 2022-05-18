import argparse
import os
import sys
import requests
import zipfile
import tarfile
import shutil
import re
from html.parser import HTMLParser

BLENDER_MIRROR_URLS = [
    'https://ftp.nluug.nl/pub/graphics/blender/release'
]

def get_platform_suffix_pattern():
    if sys.platform.startswith('linux'):
        return 'linux(-x64|64).tar.(xz|gz|bz2)'
    elif sys.platform.startswith('win64') or sys.platform.startswith('win32'):
        return 'windows(-x64|64).zip'
    else:
        raise RuntimeError(f'Unsupported platform: {sys.platform}')

class BlenderHTMLParser(HTMLParser):
    def __init__(self, blender_version_parts, convert_charrefs = ...):
        super().__init__(convert_charrefs=convert_charrefs)
        self.blender_version_parts = blender_version_parts
        self.blender_links = []
        self.platform_suffix = get_platform_suffix_pattern()

    def feed(self, data: str):
        super().feed(data)
        
        platform_pattern = re.compile(self.platform_suffix)
        platform_blender_links = []
        for link in self.blender_links:
            match = re.search(platform_pattern, link)
            if match is not None:
                platform_blender_links.append(link)
        
        if len(self.blender_version_parts) == 2:
            return platform_blender_links[-1]
        else:
            for link in platform_blender_links:
                link_blender_version = link.split('-')[1]
                if link_blender_version == '.'.join(self.blender_version_parts):
                    return link
            return None

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for name, value in attrs:
                if name == 'href' and value.startswith('blender-'):
                    self.blender_links.append(value)
                    break
        return super().handle_starttag(tag, attrs)


def get_download_url(blender_version):
    version_parts = blender_version.split('.')
    version_parts_count = len(version_parts)

    if version_parts_count != 2 and version_parts_count != 3:
        raise RuntimeError(f'Invalid Blender version: {blender_version}')

    version_major = f'{version_parts[0]}.{version_parts[1]}'

    download_folder = f'Blender{version_major}'

    download_url = None
    parser = BlenderHTMLParser(version_parts)
    for url in BLENDER_MIRROR_URLS:
        download_directory = f'{url}/{download_folder}'
        
        page = requests.get(download_directory)
        blender_archive_link = parser.feed(page.text)
        if blender_archive_link is not None:
            download_url = f'{download_directory}/{blender_archive_link}'
            break

    return download_url

def main(args):
    url = get_download_url(args.version)
    if url is None:
        raise RuntimeError(f'Cannot find mirror for Blender version {args.version}')

    print(f'Downloading Blender archive from mirror: {url}')

    archive_file_name = url.split('/')[-1]

    if not os.path.exists(archive_file_name):
        r = requests.get(url, stream=True)
        archive_file = open(archive_file_name, "wb")
        archive_file.write(r.content)
        archive_file.close()

    print(f'Extracting archive')
    if archive_file_name.endswith('zip'):
        z = zipfile.ZipFile(archive_file_name, 'r')
        zfiles = z.namelist()
        zdir = zfiles[0].split('/')[0]
    elif archive_file_name.endswith('tar.bz2') or archive_file_name.endswith('tar.gz') or archive_file_name.endswith('tar.xz'):
        z = tarfile.open(archive_file_name)
        zfiles = z.getnames()
        zdir = zfiles[0].split('/')[0]
    else:
        raise RuntimeError(f'Unknown archive extension: {archive_file_name}')

    z.extractall()
    z.close()

    extracted_dir = os.path.join(os.getcwd(), zdir)
    output_dir = os.path.join(os.getcwd(), args.out)

    os.makedirs(output_dir, exist_ok=True)
    
    for file in os.listdir(extracted_dir):
        src_path = os.path.join(extracted_dir, file)
        dst_path = os.path.join(output_dir, file)
        shutil.move(src_path, dst_path)

    shutil.rmtree(extracted_dir)

    print('Done.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Blender archive downloader.')
    parser.add_argument('version', help='Blender version')
    parser.add_argument('-o', '--out', default='blender', help='output file name')
    
    args = parser.parse_args()

    main(args)
