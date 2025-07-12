# shovel

This is a pre alpha version of Shovel, a semi-automated podcast archiving tool. 

It is generally intended to be used with .mp3 files downloaded by AudiobookShelf (ABS) (though also tested with .m4a and .ogg files; theoretically .flac and .opus should work too but I have not been able to find a feed with those filetypes to test). It does four main things which, in its finished state, will all be independently selectable:

1. Edit the ID tags of the files so as to only have one source of date data, and optionally to change the album to a new name.
This is generally needed just for ABS downloaded files. The former is done because ABS adds both "releasedate" and "date" data, and "year" data. ABS then (in a very silly manner) imports first from the "year" tag if it you export the files and import them into a new instance of ABS. That means it loses the month and day data. Shovel deletes releasedate and year, leaving only "Date". The latter is useful if you want to rename the podcast, such as if it is named "Steve's Private feed for If Books Could Kill" or similar, which is undesirable for long term archiving.

2. Rename the files in "PodcastTitle - YYYY-MM-DD - EpisodeTitle.ext" format, which allows the files to be sorted by their podcast tile (allows them to live in the same parent folder as other podcasts) and release date (the closest to a single source of truth for the order of podcast files). Again, necessary for primarily ABS downloaded files because those are named just "EpisodeTitle.ext".

3. Make a description for the archive in bbcode. For now it is not customizable, but I think it looks really snazzy. May be useful beyond files downloaded by ABS.

4. Make a torrent for the archive, can include one episode, broken down by year, one big archive for previous years and one for the current year, or yearly archives. May be useful beyond files downloaded by ABS.

## To run

python3 shovel.py input_file.txt

The input files have extensive comments and should be read for further instruction. Shovel should also give you specifics about any problematic input file if you try to run it.

Two example input files, one for a whole podcast archive, one for selecting single episodes from a wider folder is provided in addition to a blank input file template.

## PRE ALPHA NOTE

Shovel is in bad need of being cleaned up for publc viewing. My programming teachers would not be pleased at its current state. The code will be cleaned up, coding standards improved, and functions separated to relevant files based on behavior.

It is recommended to stick pretty close to the examples, as there are likely to be bugs in niche use cases. if you do want a non destructive test, consider modifying one of them by turning on dry run ("dry_run: y").

## TODOs:

In addition to cleanup and testing, the additional functionality is planned:

* Add files to a "temp" file underneath the output directory at first, to prevent filename clashes.

* Add functionality to denote a non english language archive and its language.

   
