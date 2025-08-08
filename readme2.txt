Plex Media Sorter (PyQt5 Edition) - README

User Guide

Premise

This application was designed and programmed to automate the tedious process of sorting and renaming media files for use with a Plex Media Server. It takes a folder of unsorted movies and TV shows, uses The Movie Database (TMDb) API to identify them, and then renames and moves them into a clean, Plex-compliant folder structure: Movies/[Year]/Movie Name (Year).ext and TV Shows/[Show Name]/Season [##]/S##E## - Episode Name.ext.

Installation & Setup

To run this application, you will need Python 3 and a few third-party libraries.

Install Libraries: Open your terminal or command prompt and run the following command: pip install PyQt5 tmdbv3api.

Set TMDb API Key: The application requires a free API key from The Movie Database. Sign up for an account at https://www.themoviedb.org/. Go to your account settings and generate an API key. Open the Python script (plex_sorter_pyqt5.py) and find this line (around line 30): tmdb.api_key = 'd17e73dca61aea81546e514faa5b3ff9' # Your TMDb API key. Replace the existing key with your own.

(Optional) Set Custom Logos: The UI displays two logos. To use your own, find these sections in the script and replace the file paths with the correct path to your images. Plex Logo is around line 590: plex_pixmap = QPixmap("/home/jamescreamer/Pictures/plex_logo.png").scaled(...). Your Logo is around line 700: your_pixmap = QPixmap("/home/jamescreamer/Pictures/171210048.png").scaled(...).

How to Use

Run the Script: Execute the Python file from your terminal: python plex_sorter_pyqt5.py.

Select Folders: For Unsorted Media Location, click "Browse" and choose the folder containing the media files you want to sort. For Sorted Media Destination, click "Browse" and choose the folder where you want the organized files to be saved.

Select Media Type: Movies and TV Shows sorts both types of media. TV Shows Only skips any files that don't look like a TV show episode (e.g., missing "S01E01"). Movies Only skips any files that do look like a TV show episode.

Options: If "Keep Original Files?" is checked, the application will copy the files instead of moving them, leaving your original files untouched.

Start Sorting: Click the "Start Sorting" button to begin the process.

Action Log: This window shows the step-by-step progress of the application.

Selection Pane: If the application finds multiple possible matches for a file, they will appear here. Select the correct one and click "Select", or click "Skip" to ignore that file.

Stopping the Process: "Stop Sorting" politely asks the program to finish its current file and then stop. "Force Stop" immediately kills the sorting process. Use this only if the application becomes unresponsive. A warning message is displayed below this button to remind you of its function.

Debugging

A detailed log file named media_sorter.log is automatically created in the same directory as the script. If you encounter any bugs, this file contains extremely detailed information about the program's execution, including the raw data received from the API, which is invaluable for troubleshooting.

Development History & Implementation

This project was a complete overhaul of an initial concept. I began with a functional but limited application built with Python's tkinter library and systematically upgraded it to a more robust and modern solution using PyQt5.

Initial State

The project started as a single Python script using tkinter for the user interface. It could successfully identify and sort files but lacked robust error handling, a detailed logging system, and had a less refined UI.

The Overhaul Process

My goal was to create a more professional, stable, and user-friendly application.

Migration from tkinter to PyQt5: The first major step was rebuilding the entire user interface from scratch using PyQt5. This allowed for more control over the layout and styling, resulting in a UI that closely matched my original design concept. I replaced all tkinter widgets with their PyQt5 equivalents and used layout managers (QHBoxLayout, QVBoxLayout) for a more responsive design.

Implementing a Professional Logging System: I replaced the simple print statements and custom debug functions with Python's standard logging library. I configured it to create a media_sorter.log file that captures highly detailed DEBUG level information, while simultaneously displaying cleaner, user-friendly INFO level messages in the UI's Action Log.

Threading and UI Responsiveness: To prevent the UI from freezing during long-running sorting operations, I moved the entire sorting logic into a separate QThread. I used PyQt5's native signal and slot mechanism for safe communication between the worker thread and the main UI thread. This was a significant architectural improvement over the initial tkinter implementation.

The Debugging Journey: Throughout the overhaul, I encountered and solved a series of progressively more complex bugs:

Initial Data Display Bug: The app was incorrectly displaying <built-in method title of str object...> when presenting search results. I identified that my check, hasattr(item, 'title'), was incorrectly identifying string methods as valid media titles. I fixed this by implementing a more robust check for a unique attribute (id) on the API objects.

Threading Crashes (TypeError: UILogger cannot be converted to QObject): The application was crashing with a Segmentation fault. I traced this to my custom UI logger attempting to modify the UI directly from the worker thread. I fixed this by making the logger a QObject that emits a signal, allowing the UI to be updated safely from the main thread. When that fix was incomplete, I discovered that the inheritance order was critical; class UILogger(QObject, logging.Handler) was the correct implementation.

API Data Type Mismatch (TypeError: argument 1 has unexpected type 'AsObj'): The app crashed because the tmdbv3api library returns a custom object type, not a standard Python list, which my PyQt signal was expecting. I resolved this by explicitly converting the API result to a list before emitting the signal: list(results.results).

Final API Object Usage Bug (AttributeError: 'TV' object has no attribute 'season'): After several attempts, the root cause of the final major bug was identified. The program was still crashing when trying to fetch season details. The error persisted because the tmdbv3api library requires a specific Season() object to fetch season details, not the TV() object. The fix was to import Season from the library and use Season().details(show_id, season_number) to correctly retrieve the season information. This resolved the last critical error and made the TV show sorting logic fully functional.

Improving Search Logic: My initial search logic was too simple. If a search for "sherlock holmes bbc" failed, it would give up. I implemented a far more robust aggregated search system. It now generates multiple search terms (e.g., "sherlock holmes bbc", "sherlock holmes", "sherlock"), executes all of them, and combines the unique results into a single list for the user. This dramatically increases the chances of finding the correct media. - this is still currently happening

Handling Freezes and Lock-ups: The application would freeze if the API was slow to respond, which in turn caused the UI to lock up if I tried to stop the process. I implemented a two-part solution: I added a 30-second global timeout to all API requests to prevent the worker thread from ever getting stuck indefinitely, and I changed the "Force Stop" button to use thread.terminate(), ensuring it can immediately kill a frozen worker thread and restore UI responsiveness.

This iterative process of coding, testing, and debugging has resulted in a stable, feature-rich, and reliable application.
