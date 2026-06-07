# ============================================================
# S.P.A.R.K. v3.0 – Smart Personal Assistant with Real-time Knowledge
# Built by Tanush Bhatt
# ============================================================

import time
import speech_recognition as sr
import webbrowser
import pyttsx3
import pyjokes
import requests
import wikipedia
import os
import qrcode
import pyautogui
import winsound
import re
import math
import threading
import base64
import io
import pyaudio
import numpy as np
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from PIL import Image
import google.generativeai as genai

# ── Flask App ──
app = Flask(__name__)


# ── Speech Engine ──


# ── API Keys ──
news_api_key   = "e677808e66f6496aa42682a51f38cc41"
GEMINI_API_KEY = "AIzaSyBWj7_LbDfjFP2om5-v51j00f626mmAdO0"
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")

# ── State ──
chat_history  = []
spark_awake   = True   # False = sleeping, True = awake
whisper_mode  = False   # speech-to-text mode like Wispr Flow

# ════════════════════════════════════════
# SPEAK
# ════════════════════════════════════════
def speak(text):
    print(f"SPARK: {text}")
    # Browser handles voice now


# ════════════════════════════════════════
# LISTEN
# ════════════════════════════════════════
def listen(timeout=10, phrase_limit=15):
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.3)
        r.pause_threshold  = 1
        r.energy_threshold = 300
        print("Listening...")
        try:
            audio   = r.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            command = r.recognize_google(audio, language='en-in')
            print(f"You said: {command}")
            return command.lower()
        except sr.UnknownValueError:
            return ""
        except sr.WaitTimeoutError:
            return ""
        except Exception as e:
            print(f"Listen error: {e}")
            return ""

# ════════════════════════════════════════
# CLAP DETECTION
# ════════════════════════════════════════
def detect_claps(target=2, threshold=280, gap=0.8):
    """Detects 'target' number of claps within a window."""
    pa        = pyaudio.PyAudio()
    stream    = pa.open(format=pyaudio.paInt16, channels=1,
                        rate=44100, input=True, frames_per_buffer=1024)
    clap_count = 0
    last_clap  = 0
    print(f"[CLAP DETECTOR] Waiting for {target} claps...")

    try:
        while clap_count < target:
            data      = stream.read(1024, exception_on_overflow=False)
            audio_np  = np.frombuffer(data, dtype=np.int16)
            amplitude = np.abs(audio_np).mean()

            if amplitude > threshold:
                now = time.time()
                if now - last_clap > 0.2:
                    if clap_count == 0 or (now - last_clap < gap):
                        clap_count += 1
                        last_clap   = now
                        print(f"  Clap {clap_count} detected!")
                    else:
                        clap_count = 1
                        last_clap  = now
                        print("  Reset — gap too long")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    return clap_count >= target


# ════════════════════════════════════════
# WAKE WORD LOOP
# ════════════════════════════════════════
def wake_loop():
    """Runs in background — listens for double clap then 'Spark'."""
    global spark_awake
    while True:
        try:
            if not spark_awake:
                print("[WAKE] Listening for double clap...")
                if detect_claps(target=2):
                    winsound.Beep(1200, 200)
                    speak("Yes? I'm listening.")
                    # Now wait for "spark" keyword
                    cmd = listen(timeout=5, phrase_limit=5)
                    if "spark" in cmd:
                        spark_awake = True
                        greet()
                    else:
                        speak("Say 'Spark' to wake me up.")
            else:
                time.sleep(1)
        except Exception as e:
            print(f"Wake loop error: {e}")
            time.sleep(2)

# ════════════════════════════════════════
# GREETING
# ════════════════════════════════════════
def greet():
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning, Tanush!"
    elif hour < 18:
        greeting = "Good afternoon, Tanush!"
    else:
        greeting = "Good evening, Tanush!"
    speak(greeting)
    speak("SPARK is online. All systems ready. How can I help you?")

# ════════════════════════════════════════
# GEMINI AI
# ════════════════════════════════════════
def ask_gemini(query, image=None):
    try:
        if image:
            response = gemini_model.generate_content([query, image])
        else:
            response = gemini_model.generate_content(query)
        return response.text.replace('*', '').replace('#', '').strip()
    except Exception as e:
        return f"Gemini error: {e}"

# ════════════════════════════════════════
# SCREENSHOT
# ════════════════════════════════════════
def take_screenshot():
    return pyautogui.screenshot()

# ════════════════════════════════════════
# WHISPER / SPEECH-TO-TEXT MODE
# ════════════════════════════════════════
def whisper_flow():
    """Continuously transcribes speech like Wispr Flow."""
    speak("Whisper mode activated. Speak freely. Say 'stop whisper' to exit.")
    r = sr.Recognizer()
    transcript = []
    while True:
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.2)
            try:
                audio = r.listen(source, timeout=5, phrase_time_limit=10)
                text  = r.recognize_google(audio, language='en-in')
                print(f"[WHISPER] {text}")
                transcript.append(text)
                chat_history.append({"role": "user", "text": f"[Whisper] {text}"})
                if "stop whisper" in text.lower():
                    speak("Whisper mode off.")
                    break
            except sr.UnknownValueError:
                continue
            except sr.WaitTimeoutError:
                continue
            except Exception:
                break

    # Save transcript
    if transcript:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open("whisper_transcript.txt", "a") as f:
            f.write(f"\n[{timestamp}]\n")
            f.write("\n".join(transcript))
            f.write("\n")
        speak(f"Transcript saved. {len(transcript)} lines recorded.")

# ════════════════════════════════════════
# PROCESS COMMAND
# ════════════════════════════════════════
def process_command(command):
    global spark_awake, whisper_mode
    command  = command.lower().strip()
    response = ""
    print(f"Command: {command}")

    # ── Sleep ──
    if "go to sleep" in command or "sleep spark" in command:
        spark_awake = False
        response    = "Going to sleep. Double clap and say Spark to wake me up."

    # ── Whisper Mode ──
    elif "whisper mode" in command or "start whisper" in command:
        threading.Thread(target=whisper_flow, daemon=True).start()
        return "Whisper mode started"

    # ── Open Websites ──
    elif "open google" in command:
        webbrowser.open("https://www.google.com")
        response = "Opening Google"

    elif "open youtube" in command:
        webbrowser.open("https://www.youtube.com")
        response = "Opening YouTube"

    elif "open chatgpt" in command:
        webbrowser.open("https://chat.openai.com")
        response = "Opening ChatGPT"

    elif "open stack overflow" in command:
        webbrowser.open("https://stackoverflow.com")
        response = "Opening Stack Overflow"

    elif "open github" in command:
        webbrowser.open("https://github.com")
        response = "Opening GitHub"

    elif "open linkedin" in command:
        webbrowser.open("https://www.linkedin.com")
        response = "Opening LinkedIn"

    elif "play music" in command:
        webbrowser.open("https://open.spotify.com")
        response = "Opening Spotify"

    # ── Time & Date ──
    elif "time" in command:
        response = f"The time is {datetime.now().strftime('%I:%M %p')}"

    elif "date" in command:
        response = f"Today is {datetime.now().strftime('%B %d, %Y')}"

    # ── System Apps ──
    elif "notepad" in command:
        os.startfile("notepad.exe")
        response = "Opening Notepad"

    elif "calculator" in command:
        os.startfile("calc.exe")
        response = "Opening Calculator"

    elif "command prompt" in command:
        os.startfile("cmd.exe")
        response = "Opening Command Prompt"

    elif "open downloads" in command:
        os.startfile("C:\\Users\\Tanush Bhatt\\Downloads")
        response = "Opening Downloads"

    elif "open documents" in command:
        os.startfile("C:\\Users\\Tanush Bhatt\\Documents")
        response = "Opening Documents"

    elif "open desktop" in command:
        os.startfile("C:\\Users\\Tanush Bhatt\\Desktop")
        response = "Opening Desktop"

    elif "open vs code" in command:
        os.system("code")
        response = "Opening VS Code"

    elif "open task manager" in command:
        os.system("taskmgr")
        response = "Opening Task Manager"

    # ── System Controls ──
    elif "lock" in command:
        speak("Locking the computer")
        os.system("rundll32.exe user32.dll,LockWorkStation")
        return "Computer locked"

    elif "shutdown" in command:
        speak("Shutting down in 5 seconds. Goodbye Tanush!")
        os.system("shutdown /s /t 5")
        return "Shutting down"

    elif "restart" in command:
        speak("Restarting in 5 seconds")
        os.system("shutdown /r /t 5")
        return "Restarting"

    elif "close chrome" in command or "close browser" in command:
        os.system("taskkill /F /IM chrome.exe")
        response = "Browser closed"

    elif "close vs code" in command:
        os.system("taskkill /F /IM Code.exe")
        response = "VS Code closed"

    elif "volume up" in command:
        for _ in range(5): pyautogui.press('volumeup')
        response = "Volume increased"

    elif "volume down" in command:
        for _ in range(5): pyautogui.press('volumedown')
        response = "Volume decreased"

    elif "mute" in command:
        pyautogui.press('volumemute')
        response = "Muted"

    # ── Screenshot ──
    elif "screenshot" in command:
        shot     = take_screenshot()
        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        shot.save(filename)
        os.startfile(filename)
        response = f"Screenshot saved as {filename}"

    # ── Screen Analysis ──
    elif "analyze" in command and "screen" in command or "what's on my screen" in command:
        speak("Taking screenshot. What would you like to know?")
        shot        = take_screenshot()
        img_bytes   = io.BytesIO()
        shot.save(img_bytes, format='PNG')
        img         = Image.open(io.BytesIO(img_bytes.getvalue()))
        question    = listen(timeout=8)
        query       = question if question else "Describe everything on this screen in detail."
        response    = ask_gemini(query, img)

    # ── QR Code ──
    elif "qr" in command:
        speak("What should the QR code contain?")
        winsound.Beep(1000, 200)
        data = listen(timeout=8)
        if data:
            qr       = qrcode.make(data)
            filename = f"qr_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            qr.save(filename)
            os.startfile(filename)
            response = f"QR code created for: {data}"
        else:
            response = "I couldn't hear the QR data"

    # ── Notes ──
    elif "take note" in command or "make a note" in command or "save note" in command:
        speak("What should I note?")
        winsound.Beep(1000, 200)
        note = listen(timeout=10)
        if note:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open("notes.txt", "a") as f:
                f.write(f"[{timestamp}] {note}\n")
            response = f"Note saved: {note}"
        else:
            response = "Couldn't hear the note"

    elif "read notes" in command or "show notes" in command:
        try:
            with open("notes.txt", "r") as f:
                notes = f.read()
            response = notes if notes else "No notes yet"
        except:
            response = "No notes file found"

    elif "clear notes" in command:
        open("notes.txt", "w").close()
        response = "All notes cleared"

    # ── Memory ──
    elif "remember that" in command:
        memory = command.replace("remember that", "").strip()
        with open("memory.txt", "w") as f:
            f.write(memory)
        response = "Got it, I'll remember that"

    elif "what did you remember" in command or "what do you remember" in command:
        try:
            with open("memory.txt", "r") as f:
                memory = f.read()
            response = f"You told me: {memory}" if memory else "Nothing in memory"
        except:
            response = "Memory file not found"

    # ── Math ──
    elif any(op in command for op in ["plus", "minus", "times", "divided by",
                                       "square root", "square of", "cube of"]):
        try:
            cmd = command.replace("plus", "+").replace("minus", "-")
            cmd = cmd.replace("times", "*").replace("multiplied by", "*")
            cmd = cmd.replace("divided by", "/")
            if "square root of" in cmd:
                num      = float(re.findall(r'\d+', cmd)[0])
                response = f"Square root of {int(num)} is {round(math.sqrt(num), 2)}"
            elif "square of" in cmd:
                num      = float(re.findall(r'\d+', cmd)[0])
                response = f"Square of {int(num)} is {int(num**2)}"
            elif "cube of" in cmd:
                num      = float(re.findall(r'\d+', cmd)[0])
                response = f"Cube of {int(num)} is {int(num**3)}"
            else:
                expr     = "".join(re.findall(r"[\d\.]+|\+|\-|\*|\/", cmd))
                response = f"The result is {round(eval(expr), 2)}"
        except:
            response = "Couldn't calculate that"

    # ── Jokes ──
    elif "joke" in command:
        response = pyjokes.get_joke()

    # ── Motivation ──
    elif "motivate" in command or "quote" in command or "inspire" in command:
        try:
            res      = requests.get("https://zenquotes.io/api/random", timeout=5)
            data     = res.json()
            response = f"{data[0]['q']} — {data[0]['a']}"
        except:
            response = "First they laugh at you. Then they fight you. Then you build JARVIS. Then they ask how you did it."

    # ── Weather ──
    elif "weather" in command:
        city = command.replace("weather", "").replace("in", "").strip() or "Ahmedabad"
        try:
            res      = requests.get(f"https://wttr.in/{city}?format=3", timeout=5)
            response = res.text
        except:
            response = "Couldn't fetch weather"

    # ── News ──
    elif "news" in command:
        try:
            r    = requests.get(f"https://newsapi.org/v2/top-headlines?country=in&apiKey={news_api_key}", timeout=5)
            data = r.json()
            if data["status"] == "ok":
                headlines = [a['title'] for a in data['articles'][:5]]
                response  = "Top headlines: " + ". ".join(headlines)
            else:
                response = "Couldn't fetch news"
        except:
            response = "News unavailable"

    # ── Wikipedia ──
    elif "wikipedia" in command:
        query = command.replace("wikipedia", "").strip()
        try:
            response = wikipedia.summary(query, sentences=2)
        except wikipedia.exceptions.DisambiguationError:
            response = "Too many results, be more specific"
        except:
            response = "Couldn't find that on Wikipedia"

    # ── Search ──
    elif command.startswith("search"):
        query = command[len("search"):].strip()
        webbrowser.open(f"https://www.google.com/search?q={query}")
        response = f"Searching: {query}"

    elif "youtube search" in command:
        query = command.replace("youtube search", "").strip()
        webbrowser.open(f"https://www.youtube.com/search?q={query}")
        response = f"YouTube: {query}"

    # ── Identity ──
    elif "your name" in command:
        response = "I am SPARK — Smart Personal Assistant with Real-time Knowledge. Tanush's personal AI."

    elif "how are you" in command:
        response = "All systems online. Feeling electric as always!"

    elif "what can you do" in command:
        response = ("I can open apps, browse websites, analyze your screen, "
                    "generate QR codes, take notes, tell jokes, fetch news and weather, "
                    "do math, transcribe speech, search Wikipedia, and answer anything using Gemini AI.")

    elif "who made you" in command or "who created you" in command:
        response = "I was built by Tanush Bhatt. A future Tony Stark in the making."

    # ── Exit ──
    elif "exit" in command or "goodbye" in command or "bye spark" in command:
        speak("Goodbye Tanush! SPARK going offline.")
        os._exit(0)

    # ── Gemini Fallback ──
    else:
        response = ask_gemini(command)

    speak(response)
    chat_history.append({"role": "spark", "text": response})
    return response


# ════════════════════════════════════════
# VOICE LOOP
# ════════════════════════════════════════
def voice_loop():
    global spark_awake
    while True:
        try:
            if spark_awake:
                command = listen()
                if command:
                    chat_history.append({"role": "user", "text": command})
                    process_command(command)
            else:
                time.sleep(0.5)
        except Exception as e:
            print(f"Voice loop error: {e}")
            time.sleep(1)


# ════════════════════════════════════════
# FLASK ROUTES
# ════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html", history=chat_history)

@app.route("/command", methods=["POST"])
def command_route():
    data       = request.json
    user_input = data.get("command", "").strip()
    if user_input:
        chat_history.append({"role": "user", "text": user_input})
        response = process_command(user_input)
        return jsonify({"response": response})
    return jsonify({"response": "No command received"})

@app.route("/voice", methods=["POST"])
def voice_route():
    command = listen()
    if command:
        chat_history.append({"role": "user", "text": command})
        response = process_command(command)
        return jsonify({"command": command, "response": response})
    return jsonify({"command": "", "response": "Couldn't hear anything"})

@app.route("/screenshot", methods=["POST"])
def screenshot_route():
    shot          = take_screenshot()
    img_bytes     = io.BytesIO()
    shot.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    img_base64    = base64.b64encode(img_bytes.getvalue()).decode()
    return jsonify({"screenshot": img_base64})

@app.route("/analyze", methods=["POST"])
def analyze_route():
    data      = request.json
    question  = data.get("question", "What is on this screen?")
    shot      = take_screenshot()
    img_bytes = io.BytesIO()
    shot.save(img_bytes, format='PNG')
    img       = Image.open(io.BytesIO(img_bytes.getvalue()))
    response  = ask_gemini(question, img)
    chat_history.append({"role": "user",  "text": f"[Screen] {question}"})
    chat_history.append({"role": "spark", "text": response})
    speak(response)
    return jsonify({"response": response})

@app.route("/wake", methods=["POST"])
def wake_route():
    global spark_awake
    spark_awake = True
    greet()
    return jsonify({"status": "awake"})

@app.route("/sleep", methods=["POST"])
def sleep_route():
    global spark_awake
    spark_awake = False
    speak("Going to sleep. Double clap to wake me.")
    return jsonify({"status": "sleeping"})

@app.route("/status", methods=["GET"])
def status_route():
    return jsonify({"awake": spark_awake})


# ════════════════════════════════════════
# STARTUP
# ════════════════════════════════════════
def startup():
    speak("Initializing SPARK version 3...")
    time.sleep(1)
    greet()
    speak("Double clap anytime to wake me. Or use the web interface.")

if __name__ == "__main__":
    spark_awake = True
    startup()
    wake_thread  = threading.Thread(target=wake_loop,  daemon=True)
    voice_thread = threading.Thread(target=voice_loop, daemon=True)
    wake_thread.start()
    voice_thread.start()
    print("\n[SPARK] Web UI → http://127.0.0.1:5000\n")
    app.run(debug=False, use_reloader=False)