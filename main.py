import tkinter as tk
from tkinter import messagebox
import random
import requests
import time
import threading
import queue

# --- Global Variables ---
root = None
review_frame = None
language_display_label = None
initial_load_status_label = None # Label for initial loading status
current_word_label = None
choices_frame = None
choice_buttons = []
status_label = None
feedback_label = None

LANGUAGES_SEQUENCE = ["English", "German"]
current_language_phase_index = 0
current_language_name = ""
current_question_index_in_lang = 0
MAX_QUESTIONS_PER_LANG = 5

master_initial_english_words = []
english_quiz_source_words = []
german_quiz_source_words = []

lang_code_map = {"English": "en", "German": "de"}
current_word_data = {}

api_result_queue = queue.Queue()

# --- Colors and Fonts ---
COLOR_BACKGROUND = "#E0F0E0"
COLOR_CONTENT_BG = "#D6EAF8"
COLOR_BUTTON = "#A9DFBF"
COLOR_BUTTON_TEXT = "#000000"
COLOR_WORD_TEXT = "#2C3E50"
COLOR_LANG_DISPLAY_TEXT = "#555555"
FONT_WORD = ("Arial", 32, "bold")
FONT_CHOICE_BUTTON = ("Arial", 12)
FONT_STATUS = ("Arial", 10)
FONT_FEEDBACK = ("Arial", 12, "italic")
FONT_LANG_DISPLAY = ("Arial", 10, "italic")

# --- API Functions (Core logic) ---
def fetch_random_english_words_api_core(count=1):
    try:
        url = f"https://random-word-api.vercel.app/api?words={count}"
        # print(f"Fetching from: {url}")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        words = response.json()
        if isinstance(words, list) and all(isinstance(word, str) for word in words):
            filtered_words = [word.lower() for word in words if word.isalpha() and len(word) > 2]
            
            return filtered_words
        return None
    except Exception as e:
        # print(f"Error in fetch_random_english_words_api_core: {e}")
        raise

def translate_text_mymemory_core(text, source_lang, target_lang="th"):
    if not text or not text.strip(): return None
    # print(f"Attempting to translate: '{text}' from {source_lang} to {target_lang}")
    try:
        url = f"https://api.mymemory.translated.net/get?q={requests.utils.quote(text)}&langpair={source_lang}|{target_lang}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("responseStatus") == 200:
            translated_text = data["responseData"]["translatedText"]
            error_flags = ["NO QUERY SPECIFIED!", "INVALID LANGUAGE PAIR", "PLEASE USE ISO CODE", "INTERNAL ERROR", "NO TRANSLATION FOUND"]
            if any(flag.lower() in translated_text.lower() for flag in error_flags) or len(translated_text.strip()) == 0:
                # print(f"MyMemory API issue for '{text}' to {target_lang}: Response was '{translated_text}'")
                return None
            return translated_text
        elif data.get("responseStatus") == 429:
            print(f"MyMemory API Rate Limit hit for '{text}'. Status: 429")
            return "RATE_LIMIT"
        return None
    except Exception as e:
        # print(f"Error in translate_text_mymemory_core for '{text}': {e}")
        raise

# --- Threaded API Call Wrappers ---
def call_api_in_thread(api_function, callback_id, *args):
    def target():
        try:
            result = api_function(*args)
            api_result_queue.put((callback_id, result))
        except Exception as e:
            api_result_queue.put((callback_id, e))

    thread = threading.Thread(target=target, daemon=True)
    thread.start()

# --- State Variables for Initialization Process ---
INITIALIZATION_STATE = "IDLE"
init_master_words_temp_raw = []
init_german_sources_collected = []
init_eng_for_german_idx = 0
init_english_words_for_german_candidates = []

# --- Initialization Logic (Threaded) ---
def start_initialization_process():
    global INITIALIZATION_STATE, root, initial_load_status_label, review_frame
    global master_initial_english_words, english_quiz_source_words, german_quiz_source_words
    global init_master_words_temp_raw, init_german_sources_collected, init_eng_for_german_idx, init_english_words_for_german_candidates

    master_initial_english_words = []
    english_quiz_source_words = []
    german_quiz_source_words = []
    init_master_words_temp_raw = []
    init_german_sources_collected = []
    init_eng_for_german_idx = 0
    init_english_words_for_german_candidates = []

    review_frame.pack_forget() # Hide main quiz UI
    initial_load_status_label.config(text="1/3: ดึงคำศัพท์อังกฤษตั้งต้น...")
    initial_load_status_label.place(relx=0.5, rely=0.5, anchor="center") # Show loading label
    root.update_idletasks()

    INITIALIZATION_STATE = "FETCHING_MASTER_WORDS"
    num_eng_for_eng_quiz = MAX_QUESTIONS_PER_LANG
    num_eng_to_attempt_for_german = MAX_QUESTIONS_PER_LANG + 5
    total_unique_english_words_needed_for_sources = num_eng_for_eng_quiz + num_eng_to_attempt_for_german
    num_master_words_to_fetch = total_unique_english_words_needed_for_sources * 2

    call_api_in_thread(fetch_random_english_words_api_core, "INIT_MASTER_WORDS_RESULT", num_master_words_to_fetch)
    root.after(100, process_api_queue_for_init)


def process_api_queue_for_init():
    global INITIALIZATION_STATE, root, api_result_queue, initial_load_status_label, review_frame
    global master_initial_english_words, english_quiz_source_words, german_quiz_source_words
    global init_master_words_temp_raw, init_german_sources_collected, init_eng_for_german_idx, init_english_words_for_german_candidates

    try:
        callback_id, data = api_result_queue.get_nowait()

        if INITIALIZATION_STATE == "FETCHING_MASTER_WORDS" and callback_id == "INIT_MASTER_WORDS_RESULT":
            if isinstance(data, Exception) or data is None:
                print(f"Error fetching master English words: {data}")
                INITIALIZATION_STATE = "ERROR"
            else:
                init_master_words_temp_raw = data
                processed_words = list(set(init_master_words_temp_raw))
                master_initial_english_words = [w.capitalize() for w in processed_words if len(w) >= 3 and len(w) <= 10 and w.isalpha()]
                random.shuffle(master_initial_english_words)

                num_eng_for_eng_quiz = MAX_QUESTIONS_PER_LANG
                num_eng_to_attempt_for_german = MAX_QUESTIONS_PER_LANG + 5
                total_needed_after_filter = num_eng_for_eng_quiz + num_eng_to_attempt_for_german

                if len(master_initial_english_words) < total_needed_after_filter:
                    print(f"Not enough valid master English words after filtering (need {total_needed_after_filter}, got {len(master_initial_english_words)})")
                    INITIALIZATION_STATE = "ERROR"
                else:
                    english_quiz_source_words.extend(master_initial_english_words[:num_eng_for_eng_quiz])
                    init_english_words_for_german_candidates = master_initial_english_words[num_eng_for_eng_quiz : total_needed_after_filter]
                    
                    INITIALIZATION_STATE = "TRANSLATING_GERMAN_SOURCES"
                    init_eng_for_german_idx = 0
                    init_german_sources_collected = []
                    initial_load_status_label.config(text="2/3: กำลังแปลคำศัพท์เป็นเยอรมัน...")
                    trigger_next_german_translation_in_init()

        elif INITIALIZATION_STATE == "TRANSLATING_GERMAN_SOURCES" and callback_id == "INIT_GERMAN_TRANSLATION_RESULT":
            eng_word_processed, german_translation = data 

            if isinstance(german_translation, Exception):
                print(f"Exception translating '{eng_word_processed}' to German: {german_translation}")
            elif german_translation == "RATE_LIMIT":
                print(f"Rate limit hit translating '{eng_word_processed}' to German.")
                INITIALIZATION_STATE = "ERROR" 
            else:
                is_valid_german_word = False
                if german_translation:
                    german_translation = german_translation.strip()
                    cond_word_count = (len(german_translation.split()) <= 2)
                    cond_min_length = (len(german_translation) >= 2)
                    cond_no_digits = not any(char.isdigit() for char in german_translation)
                    cond_has_some_letters = any(c.lower() in "abcdefghijklmnopqrstuvwxyzäöüß" for c in german_translation.lower())

                    if cond_word_count and cond_min_length and cond_no_digits and cond_has_some_letters:
                        is_valid_german_word = True
                
                if is_valid_german_word:
                    init_german_sources_collected.append(german_translation.capitalize())
                    print(f"Successfully translated and validated Eng->De: {eng_word_processed} -> {german_translation.capitalize()}")
                else:
                    print(f"Skipping German translation for '{eng_word_processed}'. Result: '{german_translation}'. Failed validation.")
            
            init_eng_for_german_idx += 1 
            
            if INITIALIZATION_STATE != "ERROR":
                if len(init_german_sources_collected) >= MAX_QUESTIONS_PER_LANG:
                    german_quiz_source_words.extend(init_german_sources_collected)
                    INITIALIZATION_STATE = "DONE"
                    initial_load_status_label.config(text="3/3: เตรียมข้อมูลเสร็จสิ้น!")
                    print("--- Initial Word Setup Complete (Threaded) ---") # Debug
                    # ... (rest of DONE state logic) ...
                    root.after(500, lambda: initial_load_status_label.destroy())
                    root.after(500, lambda: review_frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=20))
                    root.after(600, start_next_language_phase)
                    return 
                elif init_eng_for_german_idx < len(init_english_words_for_german_candidates):
                    trigger_next_german_translation_in_init()
                else: 
                    print(f"Ran out of English candidates ({len(init_english_words_for_german_candidates)} attempted), but only got {len(init_german_sources_collected)} German words.")
                    INITIALIZATION_STATE = "ERROR"
        
        if INITIALIZATION_STATE == "ERROR":
            messagebox.showerror("Initialization Error", "เกิดข้อผิดพลาดระหว่างการเตรียมข้อมูลชุดคำศัพท์")
            initial_load_status_label.config(text="เกิดข้อผิดพลาด!\nโปรแกรมจะปิดในไม่ช้า")
            root.after(3000, root.quit)
            return

    except queue.Empty:
        pass 
    except Exception as e:
        print(f"Unexpected error in process_api_queue_for_init: {e}")
        INITIALIZATION_STATE = "ERROR"
        messagebox.showerror("Critical Error", f"เกิดข้อผิดพลาดร้ายแรงในการประมวลผลข้อมูล: {e}")
        initial_load_status_label.config(text="ข้อผิดพลาดร้ายแรง!")
        root.after(3000, root.quit)
        return

    if INITIALIZATION_STATE not in ["DONE", "ERROR"]:
        root.after(100, process_api_queue_for_init)

def trigger_next_german_translation_in_init():
    global INITIALIZATION_STATE, init_eng_for_german_idx, init_english_words_for_german_candidates, initial_load_status_label

    if INITIALIZATION_STATE == "TRANSLATING_GERMAN_SOURCES" and \
       init_eng_for_german_idx < len(init_english_words_for_german_candidates) and \
       len(init_german_sources_collected) < MAX_QUESTIONS_PER_LANG:
        
        eng_word = init_english_words_for_german_candidates[init_eng_for_german_idx]
        initial_load_status_label.config(text=f"2/3: แปลเป็นเยอรมัน: {eng_word} ({len(init_german_sources_collected)+1}/{MAX_QUESTIONS_PER_LANG})...")
        
        def translate_eng_to_de_task(eng_word_to_trans):
            time.sleep(1.1) 
            result = translate_text_mymemory_core(eng_word_to_trans, "en", "de")
            return (eng_word_to_trans, result)

        call_api_in_thread(translate_eng_to_de_task, "INIT_GERMAN_TRANSLATION_RESULT", eng_word)

# --- State Variables for Question Preparation ---
PREPARE_QUESTION_STATE = "IDLE" 
pq_source_word_for_quiz = ""
pq_correct_thai_translation = ""
pq_distractor_eng_sources = []
pq_distractor_final_thai_translations = []
pq_current_dist_idx = 0

# --- Question Preparation Logic (Threaded) ---
def prepare_and_display_next_question():
    global PREPARE_QUESTION_STATE, pq_source_word_for_quiz, pq_correct_thai_translation
    global pq_distractor_eng_sources, pq_distractor_final_thai_translations, pq_current_dist_idx
    global current_question_index_in_lang, current_session_words_for_lang, lang_code_map, current_language_name
    global current_word_label, choice_buttons, root

    if current_question_index_in_lang >= MAX_QUESTIONS_PER_LANG: return

    pq_source_word_for_quiz = current_session_words_for_lang[current_question_index_in_lang]
    lang_code_for_thai_translation = lang_code_map[current_language_name]

    current_word_label.config(text=f"แปล: {pq_source_word_for_quiz} ({current_language_name})...")
    for btn in choice_buttons: btn.config(state=tk.DISABLED, text="...")
    root.update_idletasks()

    PREPARE_QUESTION_STATE = "GETTING_CORRECT_TRANS"
    pq_correct_thai_translation = ""
    pq_distractor_eng_sources = []
    pq_distractor_final_thai_translations = []
    pq_current_dist_idx = 0
    
    def task_get_correct_trans(word, src_lang, tgt_lang):
        time.sleep(0.6)
        return translate_text_mymemory_core(word, src_lang, tgt_lang)
    
    call_api_in_thread(task_get_correct_trans, "PQ_CORRECT_TRANS_RESULT", pq_source_word_for_quiz, lang_code_for_thai_translation, "th")
    root.after(100, process_api_queue_for_question_prep)

def process_api_queue_for_question_prep():
    global PREPARE_QUESTION_STATE, root, api_result_queue
    global pq_source_word_for_quiz, pq_correct_thai_translation
    global pq_distractor_eng_sources, pq_distractor_final_thai_translations, pq_current_dist_idx
    global current_language_name, current_word_data, current_question_index_in_lang

    try:
        callback_id, data = api_result_queue.get_nowait()

        if PREPARE_QUESTION_STATE == "GETTING_CORRECT_TRANS" and callback_id == "PQ_CORRECT_TRANS_RESULT":
            if isinstance(data, Exception) or data is None or data == "RATE_LIMIT":
                error_msg = "Rate limit" if data == "RATE_LIMIT" else f"Error: {data}"
                print(f"{error_msg} translating correct answer for '{pq_source_word_for_quiz}'")
                messagebox.showwarning("Translation Error", f"ไม่สามารถแปลคำตอบสำหรับ '{pq_source_word_for_quiz}' ({error_msg})\nจะข้ามคำถามนี้")
                PREPARE_QUESTION_STATE = "ERROR"
            else:
                pq_correct_thai_translation = data
                PREPARE_QUESTION_STATE = "GETTING_DIST_ENG_WORDS"
                num_dist_eng_needed = 2 * 3 
                call_api_in_thread(fetch_random_english_words_api_core, "PQ_DIST_ENG_RESULT", num_dist_eng_needed)

        elif PREPARE_QUESTION_STATE == "GETTING_DIST_ENG_WORDS" and callback_id == "PQ_DIST_ENG_RESULT":
            if isinstance(data, Exception) or data is None or len(data) < 2:
                print(f"Error/Not enough English words for distractors: {data}")
                pq_distractor_eng_sources = ["Random", "Word"] 
            else:
                temp_pool = list(set(data))
                random.shuffle(temp_pool)
                all_primary_eng_sources_used = set(master_initial_english_words[:MAX_QUESTIONS_PER_LANG*2])
                count = 0
                for word in temp_pool:
                    if word.capitalize() not in all_primary_eng_sources_used and \
                       word.capitalize() not in pq_distractor_eng_sources and \
                       word.lower() != pq_source_word_for_quiz.lower(): # Check against current quiz word (if English)
                        pq_distractor_eng_sources.append(word.capitalize())
                        count += 1
                    if count >= 2: break
                while len(pq_distractor_eng_sources) < 2:
                    pq_distractor_eng_sources.append(f"TempDist{len(pq_distractor_eng_sources)+1}")
            
            PREPARE_QUESTION_STATE = "TRANSLATING_DISTRACTORS"
            pq_current_dist_idx = 0 
            pq_distractor_final_thai_translations = [] 
            trigger_next_distractor_translation_pipeline()

        elif PREPARE_QUESTION_STATE == "TRANSLATING_DISTRACTORS" and callback_id.startswith("PQ_DIST_FINAL_THAI_"):
            dist_idx_processed = int(callback_id.split("_")[-1])
            
            if isinstance(data, Exception) or data is None or data == "RATE_LIMIT":
                print(f"Error/Rate Limit for final Thai distractor {dist_idx_processed}: {data}")
                pq_distractor_final_thai_translations.append(f"ตัวเลือกผิดพลาด {dist_idx_processed+1}")
            else:
                if data.lower() != pq_correct_thai_translation.lower():
                    pq_distractor_final_thai_translations.append(data)
                else:
                    pq_distractor_final_thai_translations.append(f"สุ่มเลือก {dist_idx_processed+1}")

            if len(pq_distractor_final_thai_translations) >= len(pq_distractor_eng_sources):
                while len(pq_distractor_final_thai_translations) < 2:
                    pq_distractor_final_thai_translations.append(f"ตัวเลือกสำรอง {len(pq_distractor_final_thai_translations)+1}")
                PREPARE_QUESTION_STATE = "DONE"
        
        if PREPARE_QUESTION_STATE == "DONE":
            current_word_data = {
                "word": pq_source_word_for_quiz,
                "correct_translation": pq_correct_thai_translation,
                "distractors": pq_distractor_final_thai_translations[:2] 
            }
            display_question_on_gui()
            PREPARE_QUESTION_STATE = "IDLE" 
            return 

        elif PREPARE_QUESTION_STATE == "ERROR": 
            current_question_index_in_lang += 1
            PREPARE_QUESTION_STATE = "IDLE" 
            if current_question_index_in_lang < MAX_QUESTIONS_PER_LANG:
                root.after(100, prepare_and_display_next_question)
            else:
                current_language_phase_index += 1
                root.after(100, start_next_language_phase)
            return

    except queue.Empty:
        pass 
    except Exception as e:
        print(f"Unexpected error in process_api_queue_for_question_prep: {e}")
        PREPARE_QUESTION_STATE = "ERROR" 
        messagebox.showerror("Question Prep Error", "เกิดข้อผิดพลาดในการเตรียมข้อมูลคำถามปัจจุบัน")
        current_question_index_in_lang += 1 
        if current_question_index_in_lang < MAX_QUESTIONS_PER_LANG:
             root.after(100, prepare_and_display_next_question)
        else:
            current_language_phase_index +=1
            root.after(100, start_next_language_phase)
        return

    if PREPARE_QUESTION_STATE not in ["IDLE", "DONE", "ERROR"]:
        root.after(100, process_api_queue_for_question_prep)

def trigger_next_distractor_translation_pipeline():
    global PREPARE_QUESTION_STATE, pq_current_dist_idx, pq_distractor_eng_sources, current_language_name

    if pq_current_dist_idx < len(pq_distractor_eng_sources):
        eng_dist_src = pq_distractor_eng_sources[pq_current_dist_idx]
        
        def task_translate_one_distractor(eng_word_for_dist):
            time.sleep(0.8) 
            if current_language_name == "English":
                return translate_text_mymemory_core(eng_word_for_dist, "en", "th")
            elif current_language_name == "German":
                german_intermediate = translate_text_mymemory_core(eng_word_for_dist, "en", "de")
                if german_intermediate and german_intermediate != "RATE_LIMIT":
                    time.sleep(0.8)
                    return translate_text_mymemory_core(german_intermediate, "de", "th")
                elif german_intermediate == "RATE_LIMIT":
                    return "RATE_LIMIT"
                return None
            return None

        call_api_in_thread(task_translate_one_distractor, f"PQ_DIST_FINAL_THAI_{pq_current_dist_idx}", eng_dist_src)
        pq_current_dist_idx += 1 
        
        if pq_current_dist_idx < len(pq_distractor_eng_sources): # If there's another distractor to start processing
            root.after(50, trigger_next_distractor_translation_pipeline) # Stagger start of next distractor's pipeline

# --- GUI Utility Functions ---
def setup_review_screen_widgets():
    global root, review_frame, current_word_label, choices_frame, choice_buttons, status_label, feedback_label
    review_frame = tk.Frame(root, pady=20, padx=20, bg=COLOR_CONTENT_BG)

    current_word_label = tk.Label(review_frame, text="คำศัพท์...", font=FONT_WORD, pady=20, bg=COLOR_CONTENT_BG, fg=COLOR_WORD_TEXT)
    current_word_label.pack()
    feedback_label = tk.Label(review_frame, text="", font=FONT_FEEDBACK, pady=10, bg=COLOR_CONTENT_BG)
    feedback_label.pack()
    choices_frame = tk.Frame(review_frame, bg=COLOR_CONTENT_BG, pady=10)
    choices_frame.pack()
    choice_buttons.clear()
    for i in range(3):
        button = tk.Button(choices_frame, text=f"...", font=FONT_CHOICE_BUTTON, width=18, pady=8,
                           bg=COLOR_BUTTON, fg=COLOR_BUTTON_TEXT, relief=tk.FLAT,
                           activebackground="#C0E8D5", highlightthickness=0, state=tk.DISABLED)
        button.pack(side=tk.LEFT, padx=8)
        choice_buttons.append(button)
    status_label = tk.Label(review_frame, text="", font=FONT_STATUS, pady=15, bg=COLOR_CONTENT_BG)
    status_label.pack()

def display_question_on_gui():
    global current_word_label, choice_buttons, status_label, feedback_label, current_word_data

    if not current_word_data or not current_word_data.get("word"):
        current_word_label.config(text="Error: ไม่มีข้อมูลคำถาม")
        for btn in choice_buttons: btn.config(state=tk.DISABLED, text="Error")
        return

    current_word_label.config(text=current_word_data.get("word", "N/A"))
    status_label.config(text=f"{current_language_name} - คำที่ {current_question_index_in_lang + 1}/{MAX_QUESTIONS_PER_LANG}")
    feedback_label.config(text="")

    options = [current_word_data.get("correct_translation", "N/A")] + \
              [str(d) for d in current_word_data.get("distractors", ["Dist1 N/A", "Dist2 N/A"])]
    options = [str(opt) if opt is not None else "ตัวเลือกผิดพลาด" for opt in options]
    while len(options) < 3: options.append(f"ตัวเลือกสำรอง {len(options)}")
    
    final_options = options[:3]
    random.shuffle(final_options)

    for i in range(3):
        if i < len(choice_buttons) and i < len(final_options):
            choice_buttons[i].config(text=final_options[i], state=tk.NORMAL, command=lambda opt=final_options[i]: check_answer_action(opt))
        elif i < len(choice_buttons):
             choice_buttons[i].config(text=" - ", state=tk.DISABLED)

# --- Quiz Flow Functions ---
def start_next_language_phase():
    global current_language_phase_index, current_language_name, current_question_index_in_lang
    global current_session_words_for_lang, language_display_label, english_quiz_source_words, german_quiz_source_words
    global PREPARE_QUESTION_STATE

    if PREPARE_QUESTION_STATE != "IDLE":
        root.after(200, start_next_language_phase)
        return

    if current_language_phase_index < len(LANGUAGES_SEQUENCE):
        current_language_name = LANGUAGES_SEQUENCE[current_language_phase_index]
        language_display_label.config(text=current_language_name)
        current_question_index_in_lang = 0

        if current_language_name == "English":
            current_session_words_for_lang = list(english_quiz_source_words)
        elif current_language_name == "German":
            current_session_words_for_lang = list(german_quiz_source_words)
        else: current_session_words_for_lang = []
        
        if not current_session_words_for_lang or len(current_session_words_for_lang) < MAX_QUESTIONS_PER_LANG:
            messagebox.showerror("Error", f"ชุดคำศัพท์สำหรับ {current_language_name} ไม่พร้อม ({len(current_session_words_for_lang)} คำ)")
            # root.quit() # Avoid abrupt quit, maybe allow user to see error and then close
            current_word_label.config(text=f"ผิดพลาด: ไม่มีคำศัพท์สำหรับ {current_language_name}")
            for btn in choice_buttons: btn.config(state=tk.DISABLED)
            return

        feedback_label.config(text="")
        prepare_and_display_next_question()
    else:
        finish_all_reviews_action()

def check_answer_action(selected_option):
    global current_question_index_in_lang, current_word_data, feedback_label, current_language_phase_index
    global PREPARE_QUESTION_STATE

    if not current_word_data or not current_word_data.get("word") or PREPARE_QUESTION_STATE != "IDLE":
        return

    for btn in choice_buttons: btn.config(state=tk.DISABLED)

    correct_answer = current_word_data.get("correct_translation")
    if correct_answer is None: feedback_label.config(text="Error: ไม่พบคำตอบ", fg="orange")
    elif selected_option == correct_answer: feedback_label.config(text="ถูกต้อง!", fg="green")
    else: feedback_label.config(text=f"ผิด! คำตอบคือ: {correct_answer}", fg="red")

    current_question_index_in_lang += 1
    current_word_data = {} 

    delay_ms = 2000
    if current_question_index_in_lang < MAX_QUESTIONS_PER_LANG:
        root.after(delay_ms, prepare_and_display_next_question)
    else:
        current_language_phase_index += 1
        root.after(delay_ms, start_next_language_phase)

def finish_all_reviews_action():
    messagebox.showinfo("เสร็จสิ้นทั้งหมด", "คุณทบทวนคำศัพท์ครบทุกภาษาแล้ว!")
    root.quit()

# --- Main Application Setup Function ---
def create_main_window_and_start_quiz():
    global root, language_display_label, review_frame, current_word_label, initial_load_status_label

    root = tk.Tk()
    root.title("โปรแกรมทบทวนศัพท์ (Threaded v2)")
    root.geometry("800x800")
    root.configure(bg=COLOR_BACKGROUND)

    language_display_label = tk.Label(root, text="", font=FONT_LANG_DISPLAY, bg=COLOR_BACKGROUND, fg=COLOR_LANG_DISPLAY_TEXT)
    language_display_label.place(relx=0.98, rely=0.02, anchor="ne")

    initial_load_status_label = tk.Label(root, text="กำลังเตรียมข้อมูล...", font=("Arial", 14), bg=COLOR_BACKGROUND, fg=COLOR_WORD_TEXT)
    # initial_load_status_label will be placed by start_initialization_process

    setup_review_screen_widgets() # Creates review_frame and its children

    start_initialization_process() # Starts threaded loading

    root.mainloop()


# --- Start the Application ---
if __name__ == "__main__":
    create_main_window_and_start_quiz()