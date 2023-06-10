# SCED Localization

This repository contains the script for automatically generating localized [SCED mod](https://github.com/argonui/SCED).

## Dependencies

- The [Strange Eons](https://cgjennings.ca/eons/) program. You will want to install it together with the [Arkham Horror](https://discord.com/channels/225349059689447425/249270867522093056) and the [CSV Factory](http://se3docs.cgjennings.ca/um-proj-csv-factory.html) plugins.

- Python with some packages. Install the required packages with `pip install -r requirements.txt`.

## How it works

This script uses Strange Eons to create custom Arkham Horror cards using the [ArkhamDB card translation](https://github.com/Kamalisk/arkhamdb-json-data) together with the scanned card images in the mod.

While the script can do most of things automatically, it still requires some manual configuration ahead of time. For the language you're interested in translating to, you will need to manually update the font settings to your liking in the preference panel of the Arkham Horror plugin. For many Western languages, this step is not needed since the default settings should already give good results.

The script is `main.py` in the root directory. You can run `python main.py --help` to get a list of command line options it takes. Most command line options have sensible defaults. The options are explained below:

- `--lang`

    This is the language you want to translate to. This list is restrained by what translation are available on ArkhamDB.

- `--se-executable`

    This is the path to the Strange Eons command line program. The default Windows installation gives the path `C:\Program Files\StrangeEons\bin\eons.exe`.

- `--cache-dir`

    This is a directory to keep the intermediate resources during processing. Explained in more details below.

- `--deck-images-dir`

    This is a directory to keep the translated and packed deck images. These images will be uploaded and their URLs will be referenced directly from the mod.

- `--filter`

    This is a Python expression string used to filter what cards will be translated. You can assume a variable named `card` will be available to use whose value is the data on ArkahmDB. For example `card['pack_code'] in ['core', 'rcore']` will filter for only cards in the Core and Revised Core Set.

- `--step`

    The particular step to run this automation script. Explained in more details below.

- `--repo-primary` and `--repo-secondary`

    These two paths point to the local mod repositories. If you don't provide them, the script will clone the [argonui/SCED](https://github.com/argonui/SCED) and [Chr1Z93/loadable-objects](https://github.com/Chr1Z93/loadable-objects) repsitories into the cache directory.

- `--dropbox-token`

    The Dropbox access token for uploading deck images. Explained in more details below.

The main script runs in the following steps. Each step only requires persisted data generated from the previous steps, so if you kill the script half way, you should be able to continue from the last unfinished steps.

1. *Translate* the card objects in the mod repositories. The translation data will be saved in the `SE_Generator/data` directory as CSV files.

2. *Generate* the Strange Eons script to generate a list of individual translated card images, saved in the `SE_Generator/build/images` directory.

3. *Pack* the individual translated images into deck images and save them into the deck image directory.

4. *Upload* all the translated deck images to the image host.

5. *Update* the objects in the mod repositoires.

6. *Commit* all of local filenames to match the updated image URL.

Upon finishing the above steps, the mod repositories in the cache directory will have unstaged changes ready for you to commit. If you use your own fork, you also need to manually update the [repository URL](https://github.com/argonui/SCED/blob/545181308bdb9266e0ac16005f1d51ecbde043fb/src/core/Global.ttslua#L45) in the mod.

### Cache directory

The cache directory is supposed to keep the list of intermediate resources required for processing. This includes the mod repositories, the ArkhamDB translation data, the original deck images, the cropped individual images, and maybe more.

In most cases, this directory can be deleted without affecting the output of the script. If the script cannot find something it requires, it will simply download the resources again and save them in the cache directory.

### Intermediate filenames

During processing, the script will generate a series of files with strange long filenames. Those filenames encode the necessary information for the following steps to process them. This includes the original deck image URL, the slot within the deck image, whether the image has been rotated, and maybe more.

### SE_Generator project

The `SE_Generator` directory is a self-contained Strange Eons project. This means you can open this project in the Strange Eons UI and inspect its contents, as well as running its automation script. Please note it seems that the Strange Eons UI cannot run at the same time as its command line.

### Translation directory

Some cards don't have direct entries on ArkhamDB, e.g. taboo cards, so we include their translation data in the `translations` folder. Each card will be assigned a special id. For taboo cards, the id will be the card id of the non-taboo version suffixed with `-t`.

If you want to perform any language dependent transformation on generated text, you can add a `transform.py` file and declare the corresponding [transformation functions](https://github.com/lriuui0x0/SCED_Localization/blob/master/translations/zh/transform_CN.py). You will likely need to declare an entry for `transform_victory` at least.

### Dropbox access token

To get an access token for Dropbox, you need to first [create an application](https://www.dropbox.com/developers/apps), then make sure you tick everything in the permissions tab. Generate an access token on the settings tab.

