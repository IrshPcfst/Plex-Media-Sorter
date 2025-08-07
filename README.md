Plex Media Sorter
Designed by: TheIrishPacifist

1. Project Premise

Plex Media Sorter is a graphical user interface (GUI) application built with Python and Tkinter. Its primary goal is to automate the tedious process of organizing a digital media library for use with Plex Media Server.

The application scans a user-specified folder for movie and TV show files, intelligently identifies them using an online database (either IMDb or TMDb), and then renames and moves them into a clean, Plex-compliant folder structure.

Core Features:

Automatic Identification: Uses the file or parent folder name to search an online database for the correct movie or TV series.

User-Driven Disambiguation: If multiple potential matches are found, it presents a list to the user to make the final choice.

Plex-Compliant Naming: Renames files to the standard Plex naming convention:

Movies: Movie Name (YYYY).ext

TV Shows: SXXEYY - Episode Title.ext

Correct Folder Structure: Automatically creates and sorts files into a hierarchical folder structure:

Movies: Destination/Movies/YYYY/

TV Shows: Destination/TV/YYYY/Show Name/Season XX/

Flexible Options: Allows users to sort movies, TV shows, or both, and provides an option to copy files instead of moving them.

Debugging Tools: Includes a "Force Stop" button and a "Generate Debug Log" option for troubleshooting.

2. Requirements & Setup
This project has two main versions, each relying on a different online database. Please follow the setup instructions for the version you intend to use.

For Both Versions (Required)
You will need Python 3 and the Pillow library for image handling.

pip install Pillow

Version 1: IMDb Version (Plex_Sort_Concept_IMDB.py)
This version uses the imdbpy library to fetch data from IMDb.

Installation:

pip install imdbpy

Version 2: TMDb Version (media_sorter_tmdb) - Recommended
This version is more reliable and uses The Movie Database (TMDb) API.

Installation:

pip install tmdbv3api

TMDb API Key Setup:
This version requires a free API key from TMDb.

Create a free account on themoviedb.org.

Log in, go to your account Settings, and click on the API tab in the left sidebar.

Request an API key (for personal or developer use).

Once you have your key, open the media_sorter_tmdb.py script and paste your key into this line:

tmdb.api_key = 'YOUR_API_KEY_HERE'

3. Running the Application
Ensure you have installed the required packages for the version you want to run.

Open a terminal or command prompt.

Navigate to the directory where you saved the Python script.

Run the application using Python 3:

# For the IMDb version
python3 Plex_Sort_Concept_IMDB.py

# For the TMDb version
python3 media_sorter_tmdb.py

The graphical user interface will appear. Use the "Browse" buttons to select your source and destination folders, choose your options, and click "Start Sorting".

4. Our Bug Squashing Journey 🐛
This application was developed through an iterative process of coding and debugging. Here are some of the major roadblocks we encountered and how we fixed them:

The Unreliable Search (IMDb):

Problem: The initial searches for TV shows were returning a list dominated by movies with similar names. The correct TV series was often buried or missing from the top results.

Solution: We implemented a multi-tiered search strategy. The script now searches for the full name, then progressively shorter versions (e.g., "sherlock holmes bbc" -> "sherlock holmes" -> "sherlock"), combines all the results, and intelligently sorts them to prioritize the most likely media type, ensuring the user sees the best possible matches first.

The Missing Episode Data:

Problem: After correctly identifying a TV series, the script would fail to get the episode title, reporting that the 'episodes' data was missing.

Solution: Unsolved

The Faulty Cache:

Problem: The application was caching the TV show information before the episode list had been successfully fetched. This caused every subsequent episode from the same folder to fail because it was retrieving an incomplete object from the cache.

Solution: Unsolved

The Disappearing Buttons (UI Bug):

Problem: In the redesigned UI, the "Select" and "Skip" buttons in the selection panel were not appearing correctly, making it impossible for the user to proceed.

Solution: We refactored the UI layout to make the selection panel and its buttons permanent, static elements. The buttons are now always visible and are simply enabled or disabled as needed, which fixed the layout bug.
