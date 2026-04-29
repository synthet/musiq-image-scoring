import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import os
import sys

def run_scoring(path):
    if not path:
        return
    
    path = os.path.abspath(path)
    print(f"Running scoring for: {path}")
    
    # Launch PowerShell script in a new external window so user can see progress
    cmd = [
        "powershell", 
        "-NoExit",  # Keep window open to see results
        "-ExecutionPolicy", "Bypass", 
        "-File", "Run-Scoring.ps1", 
        path  # Pass path directly, subprocess handles quoting
    ]
    
    try:
        subprocess.Popen(cmd, cwd=os.getcwd())
    except Exception as e:
        messagebox.showerror("Error", f"Failed to launch script:\n{e}")

def select_file():
    path = filedialog.askopenfilename(title="Select Image")
    run_scoring(path)

def select_folder():
    path = filedialog.askdirectory(title="Select Folder")
    run_scoring(path)

def main():
    root = tk.Tk()
    root.title("Vexlum Runner")
    root.geometry("400x300")
    
    # Style
    bg_color = "#f0f0f0"
    root.configure(bg=bg_color)
    
    lbl = tk.Label(root, text="Vexlum Scoring", font=("Arial", 16, "bold"), bg=bg_color)
    lbl.pack(pady=20)
    
    lbl_desc = tk.Label(root, text="Select a File or Folder to process:\n(Runs Hybrid Pipeline)", font=("Arial", 10), bg=bg_color)
    lbl_desc.pack(pady=10)
    
    btn_frame = tk.Frame(root, bg=bg_color)
    btn_frame.pack(pady=20)
    
    btn_file = tk.Button(btn_frame, text="📄 Process Single File", command=select_file, height=2, width=20, bg="#ffffff")
    btn_file.pack(pady=5)
    
    btn_folder = tk.Button(btn_frame, text="📂 Process Folder", command=select_folder, height=2, width=20, bg="#ffffff")
    btn_folder.pack(pady=5)
    
    lbl_footer = tk.Label(root, text="v2.5.2 Runner", font=("Arial", 8), fg="gray", bg=bg_color)
    lbl_footer.pack(side="bottom", pady=10)
    
    root.mainloop()

if __name__ == "__main__":
    main()
