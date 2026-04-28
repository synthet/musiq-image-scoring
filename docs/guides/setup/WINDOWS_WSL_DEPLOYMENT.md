# Deployment Guide: Vexlum Scoring on Windows (WSL2)

This guide provides step-by-step instructions to deploy the Vexlum Scoring on a fresh Windows 10/11 PC using WSL2 (Windows Subsystem for Linux), which is the recommended environment for GPU acceleration.

## Prerequisites

- **OS**: Windows 10 (Build 19044+) or Windows 11.
- **GPU**: NVIDIA GPU with updated drivers.
- **Permissions**: Administrator access for initial setup.

---

## Part 1: Windows & WSL2 Setup

### 1. Install NVIDIA Drivers
Ensure you have the latest **Game Ready Driver** or **Studio Driver** installed on Windows.
- Download from [NVIDIA Driver Downloads](https://www.nvidia.com/Download/index.aspx).
- *Note: You do NOT need to install CUDA on Windows itself; the driver handles WSL passthrough.*

### 2. Install WSL2
Open **PowerShell as Administrator** and run:

```powershell
wsl --install
```

After the command finishes:
1.  **Restart your computer**.
2.  After restart, a terminal window will open automatically to complete the Ubuntu installation.
3.  Create a **username** and **password** for Ubuntu when prompted.

### 3. Verify GPU in WSL
Open your **Ubuntu** terminal (search "Ubuntu" in Start menu) and run:

```bash
nvidia-smi
```
You should see your GPU details. If you see an error, ensure your Windows NVIDIA drivers are up to date.

---

## Part 2: Project Setup

### 1. Clone/Copy the Repository
You can access your Windows files from WSL at `/mnt/c/` or `/mnt/d/`.
It is recommended to keep the project on your Windows drive for easy access, or clone it directly into WSL for better filesystem performance.

**Option A: Accessing existing Windows folder (Easiest)**
Assuming project is at `/path/to/image-scoring`:
```bash
cd /path/to/image-scoring
```

**Option B: Cloning to WSL (Faster Performance)**
```bash
mkdir -p ~/projects
cd ~/projects
git clone <your-repo-url> image-scoring
cd image-scoring
```

---

## Part 3: Python Environment Setup

We will set up a Python virtual environment with **TensorFlow 2.20+** and GPU support.

### 1. Install System Dependencies
In your **Ubuntu** terminal:

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv build-essential python3-dev
```

### 2. Create Virtual Environment

**Option A — Automated (recommended):** Run from Windows:
```cmd
setup.bat
```
This creates `~/.venvs/tf`, installs dependencies, and verifies the install.

**Option B — Manual:** In WSL:
```bash
mkdir -p ~/.venvs
python3 -m venv ~/.venvs/tf
```

### 3. Activate Environment
You must activate this environment whenever you work on the project:

```bash
source ~/.venvs/tf/bin/activate
```
*(Optional) Add this to your `.bashrc` to auto-activate:*
```bash
echo "source ~/.venvs/tf/bin/activate" >> ~/.bashrc
```

### 4. Install Project Dependencies
With the clean environment activated, install the required packages.
We use the verified **WSL GPU requirements** list.

```bash
# Upgrade pip first
pip install --upgrade pip setuptools wheel

# Install dependencies
pip install -r requirements/requirements_wsl_gpu.txt
```

*If `requirements/requirements_wsl_gpu.txt` is missing, use this core list:*
```bash
pip install tensorflow[and-cuda]==2.15.0  # Or 2.20.0
pip install pillow numpy pandas scikit-learn scikit-image opencv-python-headless
pip install exifread rawpy imageio
pip install rich tqdm
```

---

## Part 4: Verification

Run the following checks to ensure everything is working.

### 1. Verify GPU Access
Create a test script `verify_gpu.py`:

```python
import tensorflow as tf
print("Num GPUs Available: ", len(tf.config.list_physical_devices('GPU')))
```

Run it:
```bash
python verify_gpu.py
```
Expected output: `Num GPUs Available: 1` (or more).

### 2. Run Vexlum Scoring
Try scoring a sample directory:

```bash
# Verify the script runs
python scripts/python/run_all_musiq_models.py --help
```

---

## Troubleshooting

- **"Command not found: wsl"**: Ensure you are on a recent version of Windows 10/11.
- **"nvidia-smi not found"**: Reinstall NVIDIA drivers on Windows.
- **"ImportError: libGL.so.1"**: Install OpenCV dependencies:
  ```bash
  sudo apt install libgl1
  ```
- **Permission Errors**: If running from `/mnt/d/`, ensure no Windows process works exclusively runs on the files.

## Summary Checklist
- [ ] NVIDIA Drivers (Windows)
- [ ] WSL2 Installed
- [ ] Ubuntu User Created
- [ ] Virtual Environment Created & Activated
- [ ] Requirements Installed
- [ ] GPU Verified
