import sys
import os
import re
import shutil
import logging
import time
from datetime import datetime

# --- Third-party libraries ---
# You need to install PyQt5 and tmdbv3api
# pip install PyQt5 tmdbv3api
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QFileDialog, QMessageBox,
                             QRadioButton, QCheckBox, QProgressBar, QTextEdit, QFrame,
                             QScrollArea)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QPalette, QColor, QPixmap, QTextCursor

from tmdbv3api import TMDb, Movie, TV, Season, exceptions

# --- TMDb API Configuration ---
# IMPORTANT: It's best practice to not hardcode API keys.
# Consider using environment variables or a config file in a real-world app.
tmdb = TMDb()
tmdb.api_key = 'd17e73dca61aea81546e514faa5b3ff9' # Your TMDb API key
tmdb.language = 'en'
tmdb.debug = False
# FIX: Set a global timeout for all API requests to prevent freezes.
tmdb.wait_on_rate_limit = True
tmdb.REQUEST_TIMEOUT = 30 # CORRECTED: Set timeout directly on the instance


# =============================================================================
# Core Sorting Logic (Now in a dedicated Worker Object)
# =============================================================================

# Define constants for video extensions and stop words
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv'}
STOP_WORDS = {'a', 'an', 'the', 'and', 'in', 'on', 'of'}


class SorterWorker(QObject):
    """
    Handles the entire sorting process in a separate thread to keep the UI responsive.
    Emits signals to communicate with the main UI thread.
    """
    # --- Signals ---
    # These signals are used to send data back to the main UI thread safely.
    log_message = pyqtSignal(str)
    total_progress_update = pyqtSignal(int, int) # max, value
    file_progress_update = pyqtSignal(int, int) # max, value
    fetching_progress_update = pyqtSignal(int, int) # max, value
    
    # Signal to request a user selection from a list of results
    # Emits: list of media objects, media_type ('tv' or 'movie')
    selection_needed = pyqtSignal(list, str) 
    
    # Signal to indicate the sorting process is finished
    finished = pyqtSignal(bool) # True if stopped by user, False otherwise

    def __init__(self, source_dir, dest_dir, sort_mode, keep_originals):
        super().__init__()
        self.source_dir = source_dir
        self.dest_dir = dest_dir
        self.sort_mode = sort_mode
        self.keep_originals = keep_originals
        
        self.is_running = True
        self.user_choice = None
        self.tv_search = TV()
        self.movie_search = Movie()
        self.folder_cache = {}

    def run(self):
        """Main entry point for the worker thread."""
        logging.info("Worker thread started.")
        try:
            self.sort_media_files()
        except Exception as e:
            logging.critical(f"An unhandled exception occurred in the worker thread: {e}", exc_info=True)
            self.log_message.emit(f"CRITICAL ERROR: {e}. Check log file for details.")
        
        # Check if the process was stopped by the user or completed naturally
        stopped_by_user = not self.is_running
        self.finished.emit(stopped_by_user)
        logging.info("Worker thread finished.")

    def stop(self):
        """Stops the sorting process."""
        self.is_running = False
        # If we are waiting for a user choice, we must set it to something
        # to unblock the worker loop.
        if self.user_choice is None:
            self.user_choice = "skip"
        logging.info("Stop signal received by worker.")

    def set_user_choice(self, choice):
        """Receives the user's selection from the main thread."""
        self.user_choice = choice
        logging.debug(f"Worker received user choice: {choice}")
    
    def _clean_filename_for_search(self, filename):
        """Cleans the filename to get a better search query."""
        name = os.path.splitext(filename)[0]
        name = re.sub(r'[sS]\d{1,2}[eE]\d{1,2}', '', name)
        name = re.sub(r'\(?(19\d{2}|20\d{2})\)?', '', name)
        name = re.sub(r'\[.*?\]', '', name)
        name = re.sub(r'\(.*?\)', '', name)
        name = re.sub(r'\b(1080p|720p|480p|dvdrip|x264|bluray|web-dl|webrip)\b', '', name, flags=re.IGNORECASE)
        name = name.replace('.', ' ').replace('_', ' ')
        return name.strip()

    def _sanitize_filename(self, name):
        """Removes characters that are illegal in filenames."""
        return re.sub(r'[\\/*?:"<>|]', "", name)

    def _find_true_show_folder(self, file_path, source_root):
        """
        Walks up from a file's path to find the show's main folder.
        """
        current_path = os.path.dirname(file_path)
        while True:
            # Stop if we reach the source root directory
            if os.path.samefile(current_path, source_root):
                return current_path
            
            folder_name = os.path.basename(current_path)
            # If folder is named "Season X", go up one level
            if re.match(r'^(season|s)\s*\d+$', folder_name, re.IGNORECASE):
                parent_path = os.path.dirname(current_path)
                # Safety check to prevent infinite loop if parent is the same as current
                if os.path.samefile(parent_path, current_path):
                    return current_path
                current_path = parent_path
            else:
                # This is the show folder
                return current_path

    def sort_media_files(self):
        """The core logic for finding, identifying, and moving media files."""
        self.log_message.emit("--- Starting Sort ---")
        
        media_files = []
        for dp, dn, fn in os.walk(self.source_dir):
            for f in fn:
                if any(f.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
                    media_files.append(os.path.join(dp, f))
        
        total_files = len(media_files)
        if total_files == 0:
            self.log_message.emit("No video files found in the source directory.")
            return

        self.total_progress_update.emit(total_files, 0)

        for i, full_path in enumerate(media_files):
            if not self.is_running:
                self.log_message.emit("--- Stop signal received. Halting process. ---")
                break

            self.total_progress_update.emit(total_files, i + 1)
            self.file_progress_update.emit(100, 0)
            
            filename = os.path.basename(full_path)
            self.log_message.emit(f"\nProcessing: {filename}")
            logging.info(f"Processing file: {full_path}")

            is_tv_show_file = re.search(r'[sS](\d{1,2})[eE](\d{1,2})', filename)
            
            if self.sort_mode == "movies" and is_tv_show_file:
                self.log_message.emit("  Sorting mode is 'Movies Only'. Skipping TV episode.")
                logging.info(f"Skipping TV episode '{filename}' due to 'Movies Only' mode.")
                continue
            if self.sort_mode == "tv" and not is_tv_show_file:
                self.log_message.emit("  Sorting mode is 'TV Shows Only'. Skipping potential movie.")
                logging.info(f"Skipping movie '{filename}' due to 'TV Shows Only' mode.")
                continue

            selected_media = None
            search_term = ""
            media_type_for_search = ""
            
            # Determine search term and type
            if is_tv_show_file:
                media_type_for_search = 'tv'
                true_show_folder_path = self._find_true_show_folder(full_path, self.source_dir)
                if true_show_folder_path in self.folder_cache:
                    selected_media = self.folder_cache[true_show_folder_path]
                    self.log_message.emit(f"  Using cached series for this folder: '{selected_media.name}'")
                    logging.debug(f"Retrieved complete series object from cache for path: {true_show_folder_path}")
                else:
                    show_folder_name = os.path.basename(true_show_folder_path)
                    search_term = self._clean_filename_for_search(show_folder_name)
                    self.log_message.emit(f"  TV episode detected. Searching for series: '{search_term}'")
            else:
                media_type_for_search = 'movie'
                search_term = self._clean_filename_for_search(filename)
                self.log_message.emit(f"  Movie file detected. Using filename for search: '{search_term}'")

            # Perform search if not cached
            if not selected_media:
                try:
                    # --- NEW: Aggregated Search Logic ---
                    self.fetching_progress_update.emit(1, 0)
                    
                    words = [word for word in search_term.lower().split(' ') if word not in STOP_WORDS]
                    search_terms = [" ".join(words[:j]) for j in range(len(words), 0, -1)]
                    
                    self.log_message.emit(f"  Generated search terms: {search_terms}")
                    logging.info(f"Generated search terms for '{search_term}': {search_terms}")
                    
                    aggregated_results = []
                    seen_ids = set()

                    for term in search_terms:
                        if not self.is_running: break
                        self.log_message.emit(f"  Searching for term: '{term}'")
                        try:
                            if media_type_for_search == 'tv':
                                results = self.tv_search.search(term)
                            else:
                                results = self.movie_search.search(term)
                            
                            logging.debug(f"RAW API Response for '{term}': {results}")
                            
                            for item in results: # tmdbv3api returns an iterator
                                if hasattr(item, 'id') and item.id not in seen_ids:
                                    aggregated_results.append(item)
                                    seen_ids.add(item.id)
                        except exceptions.TMDbException as e:
                            self.log_message.emit(f"  API request for '{term}' timed out or failed. Continuing...")
                            logging.warning(f"API request for '{term}' failed: {e}")


                    
                    self.fetching_progress_update.emit(1, 1)
                    logging.info(f"Aggregated search yielded {len(aggregated_results)} unique results.")

                    if not aggregated_results:
                        self.log_message.emit(f"  Could not find any matching media for '{search_term}'. Skipping.")
                        logging.warning(f"No results for aggregated search: '{search_term}'")
                        continue
                    
                    if len(aggregated_results) == 1:
                        selected_media = aggregated_results[0]
                    else:
                        # Emit signal to ask user for choice
                        self.user_choice = None # Reset choice
                        self.selection_needed.emit(list(aggregated_results), media_type_for_search)
                        
                        # Wait for user to make a choice
                        while self.user_choice is None and self.is_running:
                            time.sleep(0.1)
                        
                        selected_media = self.user_choice
                
                except Exception as e:
                    self.log_message.emit(f"  API search failed: {e}. Skipping.")
                    logging.error(f"API search failed for term '{search_term}': {e}", exc_info=True)
                    continue

            if not self.is_running: break # Check again after waiting for user

            if selected_media == "skip":
                self.log_message.emit("  File skipped by user.")
                logging.info(f"File '{filename}' skipped by user.")
                continue
            if not selected_media:
                self.log_message.emit("  Selection failed or was aborted. Skipping.")
                logging.warning(f"No valid media selected for '{filename}'.")
                continue

            self.file_progress_update.emit(100, 25)
            
            # Process the selected media object
            media_type = "TV" if hasattr(selected_media, 'name') else "Movies"
            
            try:
                if media_type == "TV":
                    title = selected_media.name
                    year = selected_media.first_air_date.split('-')[0] if hasattr(selected_media, 'first_air_date') and selected_media.first_air_date else "N/A"
                else: # Movie
                    title = selected_media.title
                    year = selected_media.release_date.split('-')[0] if hasattr(selected_media, 'release_date') and selected_media.release_date else "N/A"

                if year == "N/A":
                    self.log_message.emit(f"  Could not find year for '{title}'. Skipping.")
                    logging.warning(f"No year found for '{title}' (ID: {selected_media.id}).")
                    continue
                
                self.log_message.emit(f"  TMDb Match: {title} ({year}) - [{media_type}]")
                
                _, extension = os.path.splitext(filename)
                
                if media_type == "Movies":
                    new_base_name = f"{title} ({year})"
                    new_filename = f"{self._sanitize_filename(new_base_name)}{extension}"
                    destination_path = os.path.join(self.dest_dir, "Movies", str(year))
                else: # TV Show Logic
                    ep_match = re.search(r'[sS](\d+)[eE](\d+)', filename)
                    if not ep_match:
                        self.log_message.emit("  Could not find SxxExx pattern in TV file. Skipping.")
                        logging.warning(f"Could not parse SxxExx from TV file '{filename}'.")
                        continue
                    
                    season_num, episode_num = int(ep_match.group(1)), int(ep_match.group(2))
                    self.log_message.emit(f"  Detected Season {season_num}, Episode {episode_num}")
                    
                    self.fetching_progress_update.emit(1,0)
                    
                    # --- FIX: Use a new TV() object to get details and a Season() object for season info ---
                    tv_details_fetcher = TV()
                    
                    # Fetch full details to get episode info and cache it
                    # Check if the selected_media is already a detailed object from cache
                    if not hasattr(selected_media, 'seasons'):
                        show_details = tv_details_fetcher.details(selected_media.id)
                        logging.debug(f"Fetched full show details for '{show_details.name}'.")
                        if is_tv_show_file:
                             self.folder_cache[self._find_true_show_folder(full_path, self.source_dir)] = show_details
                             logging.debug("Complete series object with seasons saved to cache.")
                    else:
                        show_details = selected_media # It's already the detailed object from the cache
                        logging.debug(f"Using cached show details for '{show_details.name}'.")

                    # CORRECTED: Use the Season object to get season details
                    season_details = Season().details(show_details.id, season_num)
                    self.fetching_progress_update.emit(1,1)
                    
                    episode_title = "Unknown Episode"
                    for ep in season_details.episodes:
                        if ep.episode_number == episode_num:
                            episode_title = ep.name
                            break
                    logging.debug(f"Found episode title: '{episode_title}'")
                    
                    self.file_progress_update.emit(100, 75)
                    
                    # Pad episode number based on total episodes in season
                    total_episodes = len(season_details.episodes)
                    ep_padding = 3 if total_episodes > 99 else 2
                    
                    new_filename = f"S{season_num:02d}E{episode_num:0{ep_padding}d} - {self._sanitize_filename(episode_title)}{extension}"
                    destination_path = os.path.join(self.dest_dir, "TV Shows", self._sanitize_filename(title), f"Season {season_num:02d}")

                os.makedirs(destination_path, exist_ok=True)
                full_destination_path = os.path.join(destination_path, new_filename)
                
                operation = shutil.copy2 if self.keep_originals else shutil.move
                log_action = "Copying" if self.keep_originals else "Renaming and moving"
                self.log_message.emit(f"  {log_action} to: {full_destination_path}")
                logging.info(f"{log_action} '{full_path}' to '{full_destination_path}'")
                operation(full_path, full_destination_path)

            except Exception as e:
                self.log_message.emit(f"  ERROR processing match: {e}")
                logging.error(f"Error processing match for '{filename}': {e}", exc_info=True)
            
            self.file_progress_update.emit(100, 100)


# =============================================================================
# PyQt5 GUI Components
# =============================================================================

class UILogger(QObject, logging.Handler):
    """
    A custom logging handler that sends log records to the UI thread via a signal.
    This avoids direct UI manipulation from other threads, preventing crashes.
    """
    log_updated = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        # Correctly initialize both parent classes
        QObject.__init__(self, *args, **kwargs)
        logging.Handler.__init__(self)

    def emit(self, record):
        msg = self.format(record)
        self.log_updated.emit(msg)


class MainWindow(QMainWindow):
    """The main application window."""
    def __init__(self):
        super().__init__()
        self.worker = None
        self.thread = None
        self.selection_results = []
        self.selection_radio_buttons = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Plex Media Sorter (PyQt5 Edition)")
        self.setGeometry(100, 100, 1400, 800)
        
        # Apply a dark theme stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1f1f1f;
            }
            QFrame {
                background-color: #1f1f1f;
            }
            QWidget {
                color: #e0e0e0;
                font-family: Helvetica;
            }
            QLabel {
                color: #e5a00d; /* Plex Gold */
                font-size: 12px;
                background-color: transparent;
            }
            #TitleLabel {
                font-weight: bold;
                font-size: 14px;
            }
            #WarningLabel {
                color: #999;
                font-size: 9px;
            }
            QLineEdit {
                background-color: #333;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #e5a00d;
                color: black;
                font-size: 12px;
                font-weight: bold;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f0b429;
            }
            QPushButton:disabled {
                background-color: #555;
                color: #999;
            }
            #StopButton, #SkipButton {
                background-color: #4c4c4c;
                color: white;
            }
            #StopButton:hover, #SkipButton:hover {
                background-color: #666;
            }
            #ForceStopButton {
                background-color: #c00;
                color: white;
            }
            #ForceStopButton:hover {
                background-color: #e00;
            }
            QTextEdit, QScrollArea {
                background-color: black;
                color: #e5a00d;
                border: 1px solid #4c4c4c;
                border-radius: 4px;
            }
            QTextEdit {
                 font-family: "Courier New", monospace;
            }
            QScrollArea > QWidget > QWidget {
                background-color: black;
            }
            QProgressBar {
                border: 1px solid #4c4c4c;
                border-radius: 4px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #e5a00d;
                border-radius: 4px;
            }
            QRadioButton, QCheckBox {
                font-size: 11px;
                background-color: transparent;
            }
            QRadioButton::indicator::unchecked, QCheckBox::indicator::unchecked {
                border: 1px solid #999;
                background-color: #333;
                border-radius: 7px;
                width: 12px;
                height: 12px;
            }
            QRadioButton::indicator::checked, QCheckBox::indicator::checked {
                border: 1px solid #e5a00d;
                background-color: #e5a00d;
                border-radius: 7px;
                width: 12px;
                height: 12px;
            }
        """)

        # Main container widget and layout
        main_container = QWidget()
        self.setCentralWidget(main_container)
        outer_layout = QVBoxLayout(main_container)
        main_layout = QHBoxLayout()

        # --- Left Info Pane ---
        left_pane = QFrame()
        left_pane.setFixedWidth(250)
        left_layout = QVBoxLayout(left_pane)
        
        info_text = """
<b>Plex Media Sorter</b>
<p>Designed by<br>TheIrishPacifist</p>
<p>Programmed and<br>
designed to assist<br>
users in sorting their<br>
media library for Plex.<br>
This application could<br>
be used for other<br>
services, but please<br>
check naming<br>
requirements.</p>
<p>For Plex we use:</p>
<p>Movie Name (Year)<br>
&<br>
S00E00 - Episode<br>
Name (zeros will<br>
match the max number<br>
of episodes, ex: a<br>
season with 100<br>
episodes would be<br>
S01E001)</p>
        """
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignTop)
        
        # Plex Logo - Add your path here
        plex_logo_label = QLabel()
        try:
            # Using a placeholder path, replace with your actual path
            plex_pixmap = QPixmap("/home/jamescreamer/Pictures/plex_logo.png").scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            plex_logo_label.setPixmap(plex_pixmap)
        except Exception:
            plex_logo_label.setText("Plex Logo Not Found")

        left_layout.addWidget(info_label)
        left_layout.addStretch()
        left_layout.addWidget(plex_logo_label, alignment=Qt.AlignCenter)
        left_layout.addWidget(QLabel("<i>Not sponsored or endorsed by Plex.</i>"), alignment=Qt.AlignCenter)

        # --- Center Controls Pane ---
        center_pane = QFrame()
        center_layout = QVBoxLayout(center_pane)

        # Directory Selection
        center_layout.addWidget(QLabel("<b>Unsorted Media Location:</b>"))
        self.source_dir_edit = QLineEdit()
        center_layout.addWidget(self.source_dir_edit)
        center_layout.addWidget(self._create_browse_button(self.source_dir_edit))

        center_layout.addWidget(QLabel("<b>Sorted Media Destination:</b>"))
        self.dest_dir_edit = QLineEdit()
        center_layout.addWidget(self.dest_dir_edit)
        center_layout.addWidget(self._create_browse_button(self.dest_dir_edit))

        # Media Type Options
        center_layout.addWidget(QLabel("<b>Select Your Media Type:</b>"))
        self.radio_both = QRadioButton("Movies and TV Shows")
        self.radio_tv = QRadioButton("TV Shows Only")
        self.radio_movies = QRadioButton("Movies Only")
        self.radio_both.setChecked(True)
        center_layout.addWidget(self.radio_both)
        center_layout.addWidget(self.radio_tv)
        center_layout.addWidget(self.radio_movies)
        
        # Other Options
        self.keep_originals_check = QCheckBox("Keep Original Files?")
        self.generate_log_check = QCheckBox("Generate Debug Log?")
        self.generate_log_check.setChecked(True) # Default to on
        self.generate_log_check.setEnabled(False) # Keep it always on for now
        
        options_layout = QHBoxLayout()
        options_layout.addWidget(self.keep_originals_check)
        options_layout.addWidget(self.generate_log_check)
        center_layout.addLayout(options_layout)


        # Action Buttons
        self.start_button = QPushButton("Start Sorting")
        self.start_button.clicked.connect(self.start_sorting)
        center_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop Sorting")
        self.stop_button.setObjectName("StopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_sorting)
        center_layout.addWidget(self.stop_button)

        self.force_stop_button = QPushButton("Force Stop Process and Generate Debug Log")
        self.force_stop_button.setObjectName("ForceStopButton")
        self.force_stop_button.clicked.connect(self.force_stop)
        center_layout.addWidget(self.force_stop_button)
        
        # FIX: Add warning label for force stop button
        warning_label = QLabel("Only click this if the program is frozen. Please send me the debug log.")
        warning_label.setObjectName("WarningLabel")
        warning_label.setWordWrap(True)
        center_layout.addWidget(warning_label)


        # Progress Bars
        center_layout.addStretch()
        center_layout.addWidget(QLabel("Fetching Progress:"))
        self.fetching_progress = QProgressBar()
        center_layout.addWidget(self.fetching_progress)
        
        center_layout.addWidget(QLabel("Current File Progress:"))
        self.file_progress = QProgressBar()
        center_layout.addWidget(self.file_progress)

        center_layout.addWidget(QLabel("Overall Progress:"))
        self.total_progress = QProgressBar()
        center_layout.addWidget(self.total_progress)
        center_layout.addStretch()

        # Your Logo - Add your path here
        your_logo_label = QLabel()
        try:
            # Using a placeholder path, replace with your actual path
            your_pixmap = QPixmap("/home/jamescreamer/Pictures/171210048.png").scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            your_logo_label.setPixmap(your_pixmap)
        except Exception:
            your_logo_label.setText("Your Logo Not Found")
        center_layout.addWidget(your_logo_label, alignment=Qt.AlignCenter)


        # --- Right Log Pane ---
        right_pane = QFrame()
        right_layout = QVBoxLayout(right_pane)

        right_layout.addWidget(QLabel("<b>Action Log:</b>", objectName="TitleLabel"))
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        right_layout.addWidget(self.log_area, 2) # Give log area more space
        
        right_layout.addWidget(QLabel("<b>Selection (if needed):</b>", objectName="TitleLabel"))
        self.selection_scroll_area = QScrollArea()
        self.selection_scroll_area.setWidgetResizable(True)
        self.selection_container = QWidget()
        self.selection_layout = QVBoxLayout(self.selection_container)
        self.selection_layout.setAlignment(Qt.AlignTop)
        self.selection_scroll_area.setWidget(self.selection_container)
        right_layout.addWidget(self.selection_scroll_area, 1) # Give selection less space

        selection_button_layout = QHBoxLayout()
        self.select_button = QPushButton("Select")
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.on_select_clicked)
        self.skip_button = QPushButton("Skip")
        self.skip_button.setObjectName("SkipButton")
        self.skip_button.setEnabled(False)
        self.skip_button.clicked.connect(self.on_skip_clicked)
        selection_button_layout.addWidget(self.select_button)
        selection_button_layout.addWidget(self.skip_button)
        right_layout.addLayout(selection_button_layout)

        # Setup thread-safe logging
        log_handler = UILogger()
        log_handler.setFormatter(logging.Formatter('%(message)s'))
        log_handler.log_updated.connect(self.append_log_message) # Connect signal to slot
        logging.getLogger().addHandler(log_handler)
        logging.getLogger().setLevel(logging.INFO) # UI only needs to see INFO level and above
        
        # Add panes to main layout
        main_layout.addWidget(left_pane)
        main_layout.addWidget(center_pane)
        main_layout.addWidget(right_pane, 3) # Give right pane more weight

        help_label = QLabel("Please reach out with any bugs or check for updates at https://github.com/IrshPcfst")
        help_label.setAlignment(Qt.AlignCenter)

        outer_layout.addLayout(main_layout)
        outer_layout.addWidget(help_label)

    def append_log_message(self, message):
        """Thread-safe method to append text to the log area."""
        self.log_area.append(message)
        self.log_area.moveCursor(QTextCursor.End)

    def _create_browse_button(self, target_line_edit):
        """Helper to create a browse button."""
        button = QPushButton("Browse")
        button.clicked.connect(lambda: self.browse_directory(target_line_edit))
        return button

    def browse_directory(self, target_line_edit):
        """Opens a dialog to select a directory."""
        directory = QFileDialog.getExistingDirectory(self, "Select Directory")
        if directory:
            target_line_edit.setText(directory)

    def start_sorting(self):
        """Validates inputs and starts the sorting worker thread."""
        source = self.source_dir_edit.text()
        dest = self.dest_dir_edit.text()

        if not source or not dest or not os.path.isdir(source) or not os.path.isdir(dest):
            QMessageBox.critical(self, "Error", "Please select valid source and destination folders.")
            return

        # Determine sort mode
        if self.radio_tv.isChecked():
            sort_mode = "tv"
        elif self.radio_movies.isChecked():
            sort_mode = "movies"
        else:
            sort_mode = "both"
            
        keep_originals = self.keep_originals_check.isChecked()

        # --- Setup and start the worker thread ---
        self.thread = QThread()
        self.worker = SorterWorker(source, dest, sort_mode, keep_originals)
        self.worker.moveToThread(self.thread)

        # Connect worker signals to UI slots
        self.worker.log_message.connect(self.append_log_message)
        self.worker.total_progress_update.connect(lambda m, v: self.update_progress(self.total_progress, m, v))
        self.worker.file_progress_update.connect(lambda m, v: self.update_progress(self.file_progress, m, v))
        self.worker.fetching_progress_update.connect(lambda m, v: self.update_progress(self.fetching_progress, m, v))
        self.worker.selection_needed.connect(self.handle_selection_request)
        self.worker.finished.connect(self.on_sorting_finished)
        
        self.thread.started.connect(self.worker.run)
        
        self.thread.start()

        # Update UI state
        self.set_ui_state(is_sorting=True)
        self.log_area.clear()
        logging.info(f"Starting sort. Source: '{source}', Dest: '{dest}', Mode: '{sort_mode}', Keep Originals: {keep_originals}")

    def stop_sorting(self):
        """Signals the worker thread to stop."""
        if self.worker:
            self.worker.stop()
            self.stop_button.setText("Stopping...")
            self.stop_button.setEnabled(False)
            self.force_stop_button.setEnabled(False)

    def force_stop(self):
        """FIX: Forcefully terminate the worker thread to prevent UI lock-up."""
        if self.thread and self.thread.isRunning():
            logging.warning("--- FORCE STOP ACTIVATED ---")
            self.append_log_message("--- FORCE STOP ACTIVATED ---")
            self.thread.terminate() # Immediately kill the thread
            self.thread.wait() # Wait for termination to complete
            self.on_sorting_finished(stopped_by_user=True) # Reset the UI


    def handle_selection_request(self, results, media_type):
        """Populates the inline selection pane instead of a dialog."""
        self.clear_selection_pane()
        self.selection_results = results
        
        for item in self.selection_results:
            is_tv = hasattr(item, 'id') and hasattr(item, 'name') and hasattr(item, 'first_air_date')
            is_movie = hasattr(item, 'id') and hasattr(item, 'title') and hasattr(item, 'release_date')

            if is_tv:
                title = item.name
                year = item.first_air_date.split('-')[0] if item.first_air_date else "N/A"
                kind = "TV Series"
            elif is_movie:
                title = item.title
                year = item.release_date.split('-')[0] if item.release_date else "N/A"
                kind = "Movie"
            else:
                logging.warning(f"Skipping malformed item in selection dialog: {item}")
                continue

            text = f"{title} ({year}) - [{kind}]"
            rb = QRadioButton(text)
            self.selection_radio_buttons.append(rb)
            self.selection_layout.addWidget(rb)
        
        if self.selection_radio_buttons:
            self.selection_radio_buttons[0].setChecked(True)
            self.select_button.setEnabled(True)
            self.skip_button.setEnabled(True)

    def on_select_clicked(self):
        """Handles the 'Select' button click."""
        choice = None
        for i, rb in enumerate(self.selection_radio_buttons):
            if rb.isChecked():
                choice = self.selection_results[i]
                break
        if self.worker:
            self.worker.set_user_choice(choice)
        self.clear_selection_pane()

    def on_skip_clicked(self):
        """Handles the 'Skip' button click."""
        if self.worker:
            self.worker.set_user_choice("skip")
        self.clear_selection_pane()
    
    def clear_selection_pane(self):
        """Clears the radio buttons from the selection area."""
        for rb in self.selection_radio_buttons:
            self.selection_layout.removeWidget(rb)
            rb.deleteLater()
        self.selection_radio_buttons.clear()
        self.selection_results.clear()
        self.select_button.setEnabled(False)
        self.skip_button.setEnabled(False)

    def on_sorting_finished(self, stopped_by_user):
        """Cleans up after the worker thread is done."""
        if stopped_by_user:
            logging.info("Sorting stopped by user.")
            self.append_log_message("\n--- Sorting Stopped by User ---")
        else:
            logging.info("Sorting completed successfully.")
            self.append_log_message("\n--- Sorting Complete! ---")
            QMessageBox.information(self, "Complete", "All files have been processed!")
        
        self.set_ui_state(is_sorting=False)
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
        self.thread = None
        self.worker = None


    def update_progress(self, progress_bar, max_val, value):
        """Updates a progress bar's value."""
        if progress_bar.maximum() != max_val:
            progress_bar.setMaximum(max_val)
        progress_bar.setValue(value)

    def set_ui_state(self, is_sorting):
        """Enables or disables UI elements based on sorting state."""
        self.start_button.setEnabled(not is_sorting)
        self.stop_button.setEnabled(is_sorting)
        self.force_stop_button.setEnabled(is_sorting)
        self.stop_button.setText("Stop Sorting")
        self.source_dir_edit.setEnabled(not is_sorting)
        self.dest_dir_edit.setEnabled(not is_sorting)
        
        if not is_sorting:
            self.update_progress(self.total_progress, 1, 0)
            self.update_progress(self.file_progress, 1, 0)
            self.update_progress(self.fetching_progress, 1, 0)
            self.clear_selection_pane()

    def closeEvent(self, event):
        """Ensure the worker thread is stopped when closing the window."""
        if self.thread and self.thread.isRunning():
            self.stop_sorting()
            self.thread.quit()
            self.thread.wait()
        event.accept()


# =============================================================================
# Application Entry Point
# =============================================================================
def setup_logging():
    """Sets up the file-based logging."""
    # Configure file logging
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
    file_handler = logging.FileHandler("media_sorter.log")
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.DEBUG) # Log everything to the file

    # Get the root logger and add the file handler
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # Set root logger to lowest level
    root_logger.addHandler(file_handler)


if __name__ == "__main__":
    # Setup logging to file first
    setup_logging()
    
    # Add a message to the log file for each new run
    logging.info(f"\n{'='*50}\n--- Application Started at {datetime.now()} ---\n{'='*50}")

    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec_())
