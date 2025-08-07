import os
import re
import shutil
import imdb
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, Toplevel, Radiobutton, StringVar, Button, Label, Frame, Canvas, Scrollbar, PanedWindow, PhotoImage
from PIL import Image, ImageTk # Re-importing Pillow for robust image handling

# --- IMDb API Setup ---
ia = imdb.IMDb()

# --- Core Logic Functions ---

VIDEO_EXTENSIONS = ['.mkv', '.mp4', '.avi', '.mov', '.wmv']
STOP_WORDS = {'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 'on', 'at', 'to', 'from', 'by', 'in', 'of', 'is', 'are', 'was', 'were', 'be', 'being', 'been'}


def clean_filename_for_search(filename):
    """Cleans the filename to get a better search query for IMDb."""
    name = os.path.splitext(filename)[0]
    name = re.sub(r'[sS]\d{1,2}[eE]\d{1,2}', '', name)
    name = re.sub(r'\(?(19\d{2}|20\d{2})\)?', '', name)
    name = re.sub(r'\[.*?\]', '', name)
    name = re.sub(r'\(.*?\)', '', name)
    name = re.sub(r'\b(1080p|720p|480p|dvdrip|x264|bluray)\b', '', name, flags=re.IGNORECASE)
    name = name.replace('.', ' ').replace('_', ' ')
    return name.strip()

def sanitize_filename(name):
    """Removes characters that are illegal in filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", name)

def find_true_show_folder(file_path, source_root):
    """
    Walks up from a file's path to find the parent directory that is the show's main folder,
    not just a 'Season X' folder.
    """
    current_path = os.path.dirname(file_path)
    while True:
        if os.path.samefile(current_path, source_root):
            return current_path
        
        folder_name = os.path.basename(current_path)
        if re.match(r'^(season|s)\s*\d+$', folder_name, re.IGNORECASE):
            parent_path = os.path.dirname(current_path)
            if os.path.samefile(parent_path, current_path):
                return current_path
            current_path = parent_path
        else:
            return current_path

# --- GUI Application Class ---

class MediaSorterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Plex Media Sorter")
        self.root.geometry("1400x800") 
        self.root.configure(bg="#1f1f1f") # Dark background

        # --- Style and Color Definitions ---
        self.bg_color = "#1f1f1f"
        self.text_color = "#e5a00d" # Gold color for consistency
        self.widget_bg = "#4c4c4c"
        self.button_color = "#e5a00d"
        self.button_text_color = "black"
        
        s = ttk.Style()
        s.configure("TFrame", background=self.bg_color)
        s.configure("TLabel", background=self.bg_color, foreground=self.text_color, font=("Helvetica", 12))
        s.configure("TRadiobutton", background=self.bg_color, foreground=self.text_color, font=("Helvetica", 10))
        s.configure("TCheckbutton", background=self.bg_color, foreground=self.text_color, font=("Helvetica", 10))
        s.map("TRadiobutton", background=[('active', self.bg_color)], indicatorcolor=[('selected', self.button_color)])
        s.map("TCheckbutton", background=[('active', self.bg_color)], indicatorcolor=[('selected', self.button_color)])


        self.source_dir = tk.StringVar()
        self.dest_dir = tk.StringVar()
        self.user_choice = None
        self.sort_mode = tk.StringVar(value="both") 
        self.generate_debug_log = tk.BooleanVar(value=False)
        self.keep_original_files = tk.BooleanVar(value=False)
        self.folder_cache = {}
        self.debug_file = None
        self.selection_event = threading.Event()
        self.stop_event = threading.Event()

        # --- Main Layout Frames ---
        main_frame = Frame(root, bg=self.bg_color)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        left_info_pane = Frame(main_frame, bg=self.bg_color, width=300)
        center_controls_pane = Frame(main_frame, bg=self.bg_color, padx=20)
        right_log_pane = Frame(main_frame, bg=self.bg_color)
        
        left_info_pane.pack(side='left', fill='y', padx=(0, 10))
        center_controls_pane.pack(side='left', fill='y', expand=False)
        right_log_pane.pack(side='left', fill='both', expand=True)

        # --- Left Info Pane Content ---
        info_text = """
Designed by
TheIrishPacifist

Programmed and
designed to assist
users in sorting their
media library for Plex.
This application could
be used for other
services, but please
check naming
requirements.

For Plex we use:

Movie Name (Year)
&
S00E00 - Episode
Name (zeros will
match the max number
of episodes, ex: a
season with 100
episodes would be
S01E001)
Further functionality
may be added to sort
files into separate
Anime and OVA
sections as well.
"""
        Label(left_info_pane, text="Plex Media Sorter", font=("Helvetica", 16, "bold"), fg=self.text_color, bg=self.bg_color).pack(pady=10)
        Label(left_info_pane, text=info_text, font=("Helvetica", 10), fg=self.text_color, bg=self.bg_color, justify='left').pack(pady=10, fill='x')

        try:
            plex_img_path = "/home/jamescreamer/Pictures/plex_logo.png"
            plex_img_obj = Image.open(plex_img_path)
            plex_img_obj.thumbnail((150, 150))
            self.plex_logo = ImageTk.PhotoImage(plex_img_obj)
            Label(left_info_pane, image=self.plex_logo, bg=self.bg_color).pack(pady=20, side='bottom')
        except Exception as e:
            self.plex_logo = None
            Label(left_info_pane, text="Plex Logo\nNot Found", fg="red", bg=self.bg_color).pack(pady=20, side='bottom')
            print(f"Error loading Plex logo: {e}")

        Label(left_info_pane, text="Not sponsored or endorsed by Plex.", font=("Helvetica", 8, "italic"), fg="grey", bg=self.bg_color).pack(side='bottom')

        # --- Center Controls Pane ---
        Label(center_controls_pane, text="Unsorted Media Location:", font=("Helvetica", 12), fg=self.text_color, bg=self.bg_color).pack(anchor='w')
        source_frame = Frame(center_controls_pane, bg=self.bg_color)
        source_frame.pack(fill='x', pady=5)
        ttk.Entry(source_frame, textvariable=self.source_dir, width=40).pack(side='left', fill='x', expand=True)
        Button(source_frame, text="Browse", bg=self.button_color, fg=self.button_text_color, relief='flat', command=self.browse_source).pack(side='left', padx=5)

        Label(center_controls_pane, text="Sorted Media Destination:", font=("Helvetica", 12), fg=self.text_color, bg=self.bg_color).pack(anchor='w', pady=(10,0))
        dest_frame = Frame(center_controls_pane, bg=self.bg_color)
        dest_frame.pack(fill='x', pady=5)
        ttk.Entry(dest_frame, textvariable=self.dest_dir, width=40).pack(side='left', fill='x', expand=True)
        Button(dest_frame, text="Browse", bg=self.button_color, fg=self.button_text_color, relief='flat', command=self.browse_dest).pack(side='left', padx=5)

        Label(center_controls_pane, text="Select Your Media Type:", font=("Helvetica", 12), fg=self.text_color, bg=self.bg_color).pack(anchor='w', pady=(15,5))
        
        options_container = Frame(center_controls_pane, bg=self.bg_color)
        options_container.pack(fill='x')

        media_type_frame = Frame(options_container, bg=self.bg_color)
        media_type_frame.pack(side='left', anchor='n')
        
        ttk.Radiobutton(media_type_frame, text="Movies and TV Shows", variable=self.sort_mode, value="both", style="TRadiobutton").pack(anchor='w')
        ttk.Radiobutton(media_type_frame, text="TV Shows Only", variable=self.sort_mode, value="tv", style="TRadiobutton").pack(anchor='w')
        ttk.Radiobutton(media_type_frame, text="Movies Only", variable=self.sort_mode, value="movies", style="TRadiobutton").pack(anchor='w')

        checkbox_frame = Frame(options_container, bg=self.bg_color)
        checkbox_frame.pack(side='left', padx=20, anchor='n')
        ttk.Checkbutton(checkbox_frame, text="Generate Debug Log?", variable=self.generate_debug_log, style="TCheckbutton").pack(anchor='w')
        ttk.Checkbutton(checkbox_frame, text="Keep Original Files?", variable=self.keep_original_files, style="TCheckbutton").pack(anchor='w')
        
        self.start_button = Button(center_controls_pane, text="Start Sorting", bg=self.button_color, fg=self.button_text_color, font=("Helvetica", 12, "bold"), relief='flat', command=self.start_sorting_thread)
        self.start_button.pack(fill='x', pady=15)
        self.stop_button = Button(center_controls_pane, text="Stop Sorting", bg=self.widget_bg, fg="white", relief='flat', command=self.stop_sorting, state='disabled')
        self.stop_button.pack(fill='x')
        
        self.force_stop_button = Button(center_controls_pane, text="Force Stop Process and Generate Debug Log", bg="red", fg="white", relief='flat', command=self.force_stop)
        self.force_stop_button.pack(fill='x', pady=10)
        Label(center_controls_pane, text="Only click this if the program is frozen or acting odd. Please send me the debug log.", fg="grey", bg=self.bg_color, font=("Helvetica", 8), wraplength=350).pack()

        self.fetching_label = Label(center_controls_pane, text="Fetching Progress:", font=("Helvetica", 10), fg=self.text_color, bg=self.bg_color)
        self.fetching_label.pack(anchor='w', pady=(15,0))
        self.fetching_progress = ttk.Progressbar(center_controls_pane, orient='horizontal', length=100, mode='determinate')
        self.fetching_progress.pack(fill='x', pady=5)
        
        Label(center_controls_pane, text="Current File Progress:", font=("Helvetica", 10), fg=self.text_color, bg=self.bg_color).pack(anchor='w', pady=(15,0))
        self.file_progress = ttk.Progressbar(center_controls_pane, orient='horizontal', length=100, mode='determinate')
        self.file_progress.pack(fill='x', pady=5)

        Label(center_controls_pane, text="Overall Progress:", font=("Helvetica", 10), fg=self.text_color, bg=self.bg_color).pack(anchor='w', pady=(10,0))
        self.total_progress = ttk.Progressbar(center_controls_pane, orient='horizontal', length=100, mode='determinate')
        self.total_progress.pack(fill='x', pady=5)
        
        try:
            your_logo_path = "/home/jamescreamer/Pictures/171210048.png"
            your_logo_obj = Image.open(your_logo_path)
            your_logo_obj.thumbnail((200, 200))
            self.your_logo = ImageTk.PhotoImage(your_logo_obj)
            Label(center_controls_pane, image=self.your_logo, bg=self.bg_color).pack(pady=20)
        except Exception as e:
            self.your_logo = None
            Label(center_controls_pane, text="Your Logo\nNot Found", fg="red", bg=self.bg_color).pack(pady=20)
            print(f"Error loading your logo: {e}")

        # --- Right Log Pane ---
        Label(right_log_pane, text="Action Log:", font=("Helvetica", 12), fg=self.text_color, bg=self.bg_color).pack(anchor='w')
        self.log_area = tk.Text(right_log_pane, state='disabled', bg="black", fg=self.text_color, wrap=tk.WORD, height=15)
        self.log_area.pack(fill='both', expand=True, pady=5)
        
        Label(right_log_pane, text="Selection (if needed):", font=("Helvetica", 12), fg=self.text_color, bg=self.bg_color).pack(anchor='w', pady=(10,0))
        self.selection_container = Frame(right_log_pane, bg="black")
        self.selection_container.pack(fill='both', expand=True, pady=5)
        
        self.selection_scroll_frame = Frame(self.selection_container, bg='black')
        self.selection_scroll_frame.pack(fill='both', expand=True)

        self.selection_buttons_frame = Frame(right_log_pane, bg=self.bg_color)
        self.selection_buttons_frame.pack(fill='x', pady=5)
        
        self.select_button = Button(self.selection_buttons_frame, text="Select", bg=self.button_color, fg=self.button_text_color, relief='flat', state='disabled')
        self.skip_button = Button(self.selection_buttons_frame, text="Skip", bg=self.widget_bg, fg="white", relief='flat', state='disabled')
        self.select_button.pack(side="left", padx=10, pady=5, expand=True, fill='x')
        self.skip_button.pack(side="right", padx=10, pady=5, expand=True, fill='x')
        
        Label(root, text="Please reach out with any bugs or check for updates at https://github.com/IrshPcfst", fg="grey", bg=self.bg_color, font=("Helvetica", 8)).pack(side='bottom')


    def browse_source(self):
        directory = filedialog.askdirectory()
        if directory:
            self.source_dir.set(directory)

    def browse_dest(self):
        directory = filedialog.askdirectory()
        if directory:
            self.dest_dir.set(directory)

    def debug_log(self, message):
        if self.debug_file:
            self.debug_file.write(f"  [DEBUG] {message}\n")

    def log(self, message):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)
        if self.debug_file:
            self.debug_file.write(message + "\n")

    def start_sorting_thread(self):
        source = self.source_dir.get()
        dest = self.dest_dir.get()
        if not source or not dest:
            messagebox.showerror("Error", "Please select both source and destination folders.")
            return
        
        self.folder_cache = {}
        
        if self.generate_debug_log.get():
            try:
                self.debug_file = open("debug_log.txt", "a", encoding="utf-8")
                self.debug_file.write(f"\n--- Log started at {datetime.now()} ---\n")
            except Exception as e:
                messagebox.showerror("Error", f"Could not create debug log file: {e}")
                self.debug_file = None
        else:
            self.debug_file = None

        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.stop_event.clear()

        self.log("--- Starting Sort ---")
        thread = threading.Thread(target=self.sort_media_files, args=(source, dest))
        thread.daemon = True
        thread.start()
    
    def stop_sorting(self):
        self.log("--- Stop signal received. Finishing current file... ---")
        self.stop_event.set()
        self.stop_button.config(state="disabled")
    
    def force_stop(self):
        self.log("--- FORCE STOP ACTIVATED ---")
        self.stop_event.set() 
        self.selection_event.set() 
        if self.debug_file:
            self.debug_file.close()
            self.debug_file = None
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        messagebox.showwarning("Force Stop", "Sorting has been forcefully stopped. Debug log has been saved if enabled.")


    def populate_selection_frame(self, results):
        for widget in self.selection_scroll_frame.winfo_children():
            widget.destroy()

        canvas = Canvas(self.selection_scroll_frame, bg='black', highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.selection_scroll_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = Frame(canvas, bg='black')
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        v = StringVar(self.root, "1")
        for i, movie in enumerate(results):
            title = movie.get('title', 'N/A')
            year = movie.get('year', 'N/A')
            kind = movie.get('kind', 'N/A')
            text = f"{title} ({year}) - [{kind}]"
            rb = Radiobutton(scrollable_frame, text=text, variable=v, value=str(i+1), bg='black', fg=self.text_color, selectcolor='black', activebackground='black', activeforeground=self.text_color, justify='left')
            rb.pack(anchor="w", padx=10)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        def on_select():
            self.user_choice = results[int(v.get()) - 1]
            self.selection_event.set()
        def on_skip():
            self.user_choice = "skip"
            self.selection_event.set()
        
        self.select_button.config(command=on_select, state='normal')
        self.skip_button.config(command=on_skip, state='normal')

    def clear_selection_frame(self):
        for widget in self.selection_scroll_frame.winfo_children():
            widget.destroy()
        self.select_button.config(state='disabled')
        self.skip_button.config(state='disabled')

    def show_completion_message(self, stopped=False):
        if stopped:
            self.log("\n--- Sorting Stopped by User ---")
        else:
            self.log("\n--- Sorting Complete! ---")
        
        if self.debug_file:
            self.debug_file.close()
            self.debug_file = None
        
        if not stopped:
            messagebox.showinfo("Complete", "All files have been processed.")
        
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.total_progress['value'] = 0
        self.file_progress['value'] = 0
        self.fetching_progress['value'] = 0

    def sort_media_files(self, source, dest):
        mode = self.sort_mode.get()
        media_files = [os.path.join(dp, f) for dp, dn, fn in os.walk(source) for f in fn if any(f.lower().endswith(ext) for ext in VIDEO_EXTENSIONS)]
        total_files = len(media_files)
        if total_files == 0:
            self.root.after(0, self.show_completion_message)
            return
        self.total_progress['maximum'] = total_files

        for i, full_path in enumerate(media_files):
            if self.stop_event.is_set():
                self.root.after(0, self.show_completion_message, True)
                return

            filename = os.path.basename(full_path)
            self.log(f"\nProcessing: {filename}")
            self.file_progress['value'] = 0
            self.total_progress['value'] = i + 1

            is_tv_show_file = re.search(r'[sS](\d{1,2})[eE](\d{1,2})', filename)
            
            if mode == "movies" and is_tv_show_file:
                self.log("  Sorting mode is 'Movies Only'. Skipping TV episode.")
                continue
            if mode == "tv" and not is_tv_show_file:
                self.log("  Sorting mode is 'TV Shows Only'. Skipping potential movie.")
                continue

            selected_media = None
            search_term = ""
            
            if is_tv_show_file:
                true_show_folder_path = find_true_show_folder(full_path, source)
                if true_show_folder_path in self.folder_cache:
                    selected_media = self.folder_cache[true_show_folder_path]
                    self.log(f"  Using cached series for this folder: '{selected_media.get('title')}'")
                    self.debug_log(f"Retrieved complete series object from cache. Has episodes: {'episodes' in selected_media}")
                else:
                    show_folder_name = os.path.basename(true_show_folder_path)
                    search_term = clean_filename_for_search(show_folder_name)
                    self.log(f"  TV episode detected. Searching for series: '{search_term}'")
            else:
                search_term = clean_filename_for_search(filename)
                self.log(f"  Movie file detected. Using filename for search: '{search_term}'")

            if not selected_media:
                try:
                    search_terms = [search_term]
                    words = [word for word in search_term.lower().split(' ') if word not in STOP_WORDS]
                    if len(words) > 1:
                        for j in range(len(words) - 1, 0, -1):
                            search_terms.append(" ".join(words[:j]))
                    
                    combined_results = {}
                    for term in search_terms:
                        self.debug_log(f"Searching for term: '{term}'")
                        results = ia.search_movie(term)
                        for result in results:
                            combined_results[result.movieID] = result
                    
                    final_results = list(combined_results.values())
                    self.debug_log(f"Combined search yielded {len(final_results)} unique results.")

                    if len(final_results) > 1:
                        self.root.after(0, self.fetching_progress.config, {'maximum': len(final_results), 'value': 0})
                        self.log(f"  Pre-fetching details for all {len(final_results)} results...")
                        for idx, result in enumerate(final_results):
                            if self.stop_event.is_set(): break
                            ia.update(result)
                            self.root.after(0, self.fetching_progress.config, {'value': idx + 1})
                        self.debug_log("Pre-fetching complete.")

                    if is_tv_show_file:
                        final_results = [r for r in final_results if 'series' in r.get('kind', '').lower()]
                        self.debug_log(f"After filtering for TV series, {len(final_results)} results remain.")
                    else:
                        final_results = [r for r in final_results if 'series' not in r.get('kind', '').lower()]
                        self.debug_log(f"After filtering for movies, {len(final_results)} results remain.")

                    if not final_results:
                        self.log(f"  Could not find any matching media for '{search_term}'. Skipping.")
                        continue
                    
                    if len(final_results) == 1:
                        selected_media = final_results[0]
                    else:
                        self.selection_event.clear()
                        self.root.after(0, self.populate_selection_frame, final_results)
                        self.selection_event.wait()
                        self.root.after(0, self.clear_selection_frame)
                        selected_media = self.user_choice
                    
                    self.debug_log(f"User selected: {selected_media}")

                except Exception as e:
                    self.log(f"  IMDb search failed: {e}. Skipping.")
                    continue

            if selected_media == "skip":
                self.log("  File skipped by user.")
                continue
            if not selected_media:
                self.log("  Selection failed. Skipping.")
                continue

            self.file_progress['value'] = 25

            # --- BUG FIX: Consolidated and corrected detail fetching ---
            try:
                self.log(f"  Verifying details for: {selected_media.get('title')}")
                if 'series' in selected_media.get('kind', '').lower():
                    self.debug_log("Item is a series. Ensuring episode data is present.")
                    ia.update(selected_media, ['main', 'episodes'])
                    self.debug_log(f"Fetch complete. Has episodes: {'episodes' in selected_media}")
                    # Cache the complete object now
                    if is_tv_show_file and not self.folder_cache.get(true_show_folder_path):
                         self.folder_cache[true_show_folder_path] = selected_media
                         self.debug_log("Complete series object saved to cache.")
                else:
                    ia.update(selected_media) # Standard update for movies
            except Exception as e:
                self.log(f"  Failed to fetch details: {e}")
                continue
            self.file_progress['value'] = 50
            
            kind = selected_media.get('kind', 'movie')
            media_type = "TV" if 'series' in kind.lower() else "Movies"
            
            year = selected_media.get('year')
            title = selected_media.get('title', 'Unknown Title')
            if not year:
                self.log(f"  Could not find year for '{title}'. Skipping.")
                continue
            
            self.log(f"  IMDb Match: {title} ({year}) - [{media_type}]")
            
            _, extension = os.path.splitext(filename)
            
            if media_type == "Movies":
                new_base_name = f"{title} ({year})"
                new_filename = f"{sanitize_filename(new_base_name)}{extension}"
                destination_path = os.path.join(dest, "Movies", str(year))
            else: # TV Show Logic
                ep_match = re.search(r'[sS](\d{1,2})[eE](\d{1,2})', filename)
                if not ep_match:
                    self.log("  File was identified as a TV show by user, but couldn't find SxxExx pattern. Skipping.")
                    continue
                
                season_num, episode_num = int(ep_match.group(1)), int(ep_match.group(2))
                self.log(f"  Detected Season {season_num}, Episode {episode_num}")
                
                try:
                    episode = selected_media['episodes'][season_num][episode_num]
                    self.debug_log(f"Successfully accessed episode object: {episode.data}")
                    episode_title = episode.get('title', f'Episode {episode_num}')
                except Exception as e:
                    self.log(f"  Could not find episode details in data: {e}. Skipping.")
                    continue
                
                self.file_progress['value'] = 75
                
                new_filename = f"S{season_num:02d}E{episode_num:02d} - {sanitize_filename(episode_title)}{extension}"
                destination_path = os.path.join(dest, "TV", str(year), sanitize_filename(title), f"Season {season_num}")

            os.makedirs(destination_path, exist_ok=True)
            full_destination_path = os.path.join(destination_path, new_filename)
            
            try:
                operation = shutil.copy if self.keep_original_files.get() else shutil.move
                log_action = "Copying" if self.keep_original_files.get() else "Renaming and moving"
                self.log(f"  {log_action} to: {full_destination_path}")
                operation(full_path, full_destination_path)
            except Exception as e:
                self.log(f"  ERROR performing file operation: {e}")
            
            self.file_progress['value'] = 100

        self.root.after(0, self.show_completion_message)

if __name__ == "__main__":
    root = tk.Tk()
    app = MediaSorterApp(root)
    root.mainloop()

