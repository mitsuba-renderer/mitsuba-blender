import argparse
from zipfile import ZipFile
import os

def main(args):
    addon_name = 'mitsuba2-blender'
    base_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    addon_dir = os.path.join(base_dir, addon_name)

    with ZipFile('mitsuba-blender.zip', 'w') as archive:
        # Package miscellaneous files
        miscellaneous_files = ['README.md', 'LICENSE']
        for filename in miscellaneous_files:
            filepath = os.path.join(base_dir, filename)
            archivepath = os.path.join(addon_name, filename)
            archive.write(filepath, archivepath)

        # Package addon source files
        for folder, _, filenames in os.walk(addon_dir):
            # Filter out Python cache directories
            if folder.endswith('__pycache__'):
                continue
            for filename in filenames:
                if filename.endswith('.py') or filename.endswith('.json'):
                    filepath = os.path.join(folder, filename)
                    shortpath = os.path.relpath(filepath, base_dir)
                    archive.write(filepath, shortpath)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    main(args)
