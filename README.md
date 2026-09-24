# Image Personalizer

A barebones local app: enter a few preferences, generate an image, give it a score
from 0–100, and let those scores guide the next prompt.

## Requirements

Image Personalizer connects two separately installed services: **Ollama** writes
prompts and **ComfyUI** generates images. This repository includes the app and its
workflow, but does not include those services, GPU drivers, or model downloads.

- **Python 3.12 or newer**, with `venv` and pip, plus **Git**.
- **Ollama** with the prompt model listed below.
- **ComfyUI** with Qwen Image 2.1 support and the three model files listed below.
- Hardware capable of running the included ComfyUI workflow and Ollama model.
  The tested setup is Ubuntu, an NVIDIA RTX 5090 with 32 GB VRAM, and 64 GB RAM.
  This is a tested configuration, not a measured minimum. Other GPUs and operating
  systems have not been verified for this project. Allow disk space for the large
  model downloads and for generated images.

The shell scripts target Linux/Bash. Windows PowerShell commands are provided
below for the app; ComfyUI and Ollama must also work on your chosen platform.
No Node.js, hosted API key, or cloud service is required to run the app.

## Install

### 1. Get the application

Install Git and Python first. On Ubuntu, for example:

```bash
sudo apt update
sudo apt install git curl python3 python3-venv python3-pip
python3 --version
```

Check that the reported Python version is **3.12 or newer**. Older Ubuntu releases
may need a newer Python installation before proceeding. On Windows, install
[Python](https://www.python.org/downloads/) and [Git](https://git-scm.com/downloads),
then open PowerShell and check `py -3.12 --version` (substitute a newer installed
version if needed).

In a terminal, navigate to the parent folder where you want the project and run:

```bash
git clone https://github.com/rrk01/image-personalizer.git
cd image-personalizer
```

Keep this folder separate from your ComfyUI installation. Neither folder needs a
particular name or location; the app communicates with ComfyUI over its local API.

### 2. Install Ollama and download the prompt model

Follow the [Ollama Linux installation instructions](https://docs.ollama.com/linux)
or use the [Ollama installer for your platform](https://ollama.com/download).
On Linux, the official installation command is:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

With Ollama running, download the exact model used by the app:

```bash
ollama pull qwen3-vl:8b-instruct-q4_K_M
ollama list
```

The model should appear in the list. See its
[Ollama model page](https://ollama.com/library/qwen3-vl:8b-instruct-q4_K_M).
If Ollama is not running as a background service, run `ollama serve` in a separate
terminal and leave it open. Do not start a second server if one is already running.
The default API address is `http://127.0.0.1:11434`.

This Ollama model is separate from ComfyUI's text encoder. Both are needed; a
`.safetensors` file in ComfyUI does not install the Ollama model.

### 3. Set up ComfyUI and its image models

Install ComfyUI and the GPU dependencies appropriate for your hardware using the
[official installation guide](https://docs.comfy.org/installation/manual_install).
Use a separate Python environment for ComfyUI and Image Personalizer.

Download these exact files from the
[Comfy-Org Qwen Image 2.1 repository](https://huggingface.co/Comfy-Org/Qwen-Image-2.1)
and place them in the folders shown, relative to your **ComfyUI installation**:

| Download | Destination folder |
| --- | --- |
| [qwen_image_2.1_int8_convrot.safetensors](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/diffusion_models/qwen_image_2.1_int8_convrot.safetensors) | `ComfyUI/models/diffusion_models/` |
| [qwen3vl_8b_int8_convrot.safetensors](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/text_encoders/qwen3vl_8b_int8_convrot.safetensors) | `ComfyUI/models/text_encoders/` |
| [qwen_image_2.1_vae_bf16.safetensors](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/vae/qwen_image_2.1_vae_bf16.safetensors) | `ComfyUI/models/vae/` |

Keep the filenames exactly as shown, directly inside those folders. The included
API workflow expects these names. If you use subfolders, the corresponding loader
filenames in `workflows/qwen_image_2_1.json` must include those subfolders.

Start ComfyUI using its installation's launcher. For a manual installation,
activate **ComfyUI's own environment**, open its folder, and run `python main.py`.
The default address is [http://127.0.0.1:8188](http://127.0.0.1:8188).

Open `workflows/source_qwen_image_2_1.json` from this repository in the ComfyUI
interface, enter a short prompt, and generate one image successfully before
continuing. If nodes such as `TextEncodeQwenImage21`, `ResolutionSelector`, or
`SaveImageAdvanced` are missing, update ComfyUI using its official update
instructions. These are built-in nodes in the supported workflow.

### 4. Install the app dependencies

Back in the **image-personalizer** project folder, run:

```bash
./setup.sh
```

This creates `.venv`, installs the pinned dependencies in `requirements.lock`,
and installs the app. It does not install or start ComfyUI or Ollama. You do not
need to activate `.venv` when using the provided scripts.

On Windows PowerShell, use these commands instead:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

### 5. Configure service addresses (optional)

The defaults work when both services run on the same computer at their standard
ports. To customize them, copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

In PowerShell, use `Copy-Item .env.example .env`. Edit the new file:

```dotenv
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3-vl:8b-instruct-q4_K_M
COMFYUI_URL=http://127.0.0.1:8188
DATA_DIR=data
```

`OLLAMA_MODEL` must match an installed model name in `ollama list`. The listed
model is the tested default; other models must support the app's structured JSON
responses. `DATA_DIR` can be relative to the project folder or an absolute path.
Restart the app after configuration changes. `.env` and local data are excluded
from Git.

## Start and stop

Keep Ollama and ComfyUI running. From the project folder:

```bash
./start.sh
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [Image Personalizer](http://127.0.0.1:8000). The page should show **Ollama ·
ready** and **ComfyUI · ready**. You can now enter starting ideas and generate an
image. The first generation may take longer while models load.

Stop the app with **Ctrl+C** in its terminal. This leaves Ollama and ComfyUI
running. If a ComfyUI image job is already running, it may finish there; restart
the app and use **Retry generation** to recover it. Saved sessions remain on disk.

This MVP serves one local user, with one app process and one generation at a time.
Use the loopback address above; public hosting and authentication are not included.

## Use

1. Enter starting ideas, such as `Japanese, floral`, and optionally a session name.
2. Choose an **Aspect ratio for the next image**, set Mutation (20% by default),
   and click **Generate first image**.
3. Enter an integer score from 0–100 and optional written feedback (up to 1,000
   characters), such as “Love the colors; try a simpler background.”
4. Choose **Save rating only** to stop here, or **Save & generate next** to continue.
   You can edit the latest image's saved score and feedback until you generate its successor.
5. Adjust Mutation and aspect ratio between generations if desired. The ratio is
   saved with your session when you generate or save a rating. Saving a rating
   only can save the next ratio without changing the current image.
6. **New session** starts fresh. Use **Saved sessions → Open** to return to a
   previous session's last image. Sessions save automatically; score and feedback
   edits require a save button. You can rename a session using **Rename**.

Mutation is a probability, decided by the application for each image. At 0%,
the LLM refines promising directions. At 100%, it explores a new direction each
time. Both modes retain the starting ideas. A random image seed still introduces
variation at 0%. The first generation interprets the ideas without rating history.

Aspect ratios: **1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9, and 21:9**. All use the
workflow's one-megapixel target, rounded to multiples of 16 to match Qwen 2.1's
VAE; the selector shows the resulting pixel dimensions. The current image's ratio and dimensions
are displayed separately. The LLM receives the chosen format to guide composition
and the original ratios of its scored examples. Retry retains the failed image's
original format. Older sessions and images default to 1:1.

The LLM receives up to ten distinct scored examples: four highest-rated, two
lowest-rated, and four most recent (overlaps are included once), including their
written feedback. It also receives the count, mean, best score, and population
standard deviation of **all saved scores in that session**. These statistics are
displayed beside the image controls; standard deviation measures score spread
and appears after two ratings. The model is cautioned that fewer than five ratings
provide limited evidence and equal scores do not imply confidence. This is prompting
with stored feedback, not model training. Ratings suggest preferences; they don't
prove that a particular phrase caused a better image or guarantee rising scores.

Refreshing or reopening the page restores the active session, including its latest
saved score and feedback. **Save rating only** updates that image without creating
a job. **Save & generate next** saves the rating and creates the next generation
together; duplicate submissions return the same successor. Each session uses only
its own ratings and feedback. Switching sessions is disabled during generation.
Retry preserves an existing prompt and seed and reconnects to an existing ComfyUI job where possible.

## How generation runs

Avoid running separate Ollama chats or ComfyUI jobs during generation. The app
checks the ComfyUI queue before freeing models or submitting an image. Run one
app process; do not add multiple Uvicorn workers.

The application requests ComfyUI model unloading before writing a new prompt,
waits for its GPU allocations to clear, then calls Ollama. LLM responses have a
512-token cap, a 16,384-token context window, and a three-minute request timeout.
Ollama uses `keep_alive: 0`, with an explicit unload check before image generation. ComfyUI models may remain
loaded while you rate an image and are freed before the next LLM turn. Image jobs
have a twenty-minute observation timeout; Retry reconnects to a still-running job.

## Workflow

`workflows/source_qwen_image_2_1.json` is the included visual workflow for testing
in ComfyUI. The app uses `workflows/qwen_image_2_1.json`, its flattened API graph,
with these settings:

- Qwen Image 2.1 INT8 ConvRot, Qwen3-VL 8B INT8 ConvRot encoder, BF16 VAE
- ResolutionSelector: selected aspect ratio, 1 megapixel, multiple of 16
  (square defaults to 1024×1024)
- 25 steps, CFG 1, Euler sampler, simple scheduler, denoise 1, batch size 1
- Empty negative prompt; PNG 8-bit sRGB output

The app overrides the source workflow's multiple-of-eight rounding with 16 for
new generations, so the decoder does not silently round non-square sizes again.
Each run sets the positive prompt, seed, and selected aspect ratio. Output names use
`ImagePersonalizer/<generation-id>` to keep app jobs identifiable in ComfyUI.
This MVP intentionally targets this workflow's node IDs rather than importing
arbitrary workflows. The ComfyUI installation and model files are not modified.

## Files

```text
app/                  FastAPI endpoints, SQLite store, preference selection
app/services/         Ollama, ComfyUI and generation coordination
web/                  HTML, CSS and JavaScript; no frontend build step
workflows/            Original visual workflow and runnable API graph
tests/                State, rating, recovery and service integration tests
data/                 Local database and images (excluded from Git)
```

`data/personalizer.sqlite3` stores named sessions, aspect ratios, scores, written feedback, prompts, seeds, mutation
decisions, exact submitted workflow graphs, and LLM request context.
`data/images/` stores independent copies of completed PNGs. Removing a ComfyUI
output does not remove the app's saved copy. Back up the entire `data/` folder
with the app stopped. When an existing database needs a schema upgrade, the app
creates a SQLite backup in `data/backups/` before adding any missing session names, feedback,
or aspect-ratio fields.
Existing sessions get names from their starting preferences; their scores and
images are retained. Migration backups cover the database; back up `data/images/`
as well for a complete copy. Local data and backups are excluded from Git.

## Update

Stop the app, back up your data folder, then run from the project folder:

```bash
git pull --ff-only
./setup.sh
./start.sh
```

On Windows, run `git pull --ff-only`, repeat the two pip commands from step 4,
then use the PowerShell startup command. Refresh the browser after restarting.
If Git reports local changes, preserve or commit those changes before updating.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| `python3` is too old | Install Python 3.12+ and make sure `python3 --version` reports it before using `setup.sh`. |
| `venv` or `ensurepip` is missing | Install the venv package matching your Python version; on Ubuntu's default Python, use `sudo apt install python3-venv`. |
| `Permission denied` for a shell script | Run `bash setup.sh` or `bash start.sh` from the project folder. |
| Ollama is offline | Start the Ollama app/service or `ollama serve`; check `OLLAMA_URL` in `.env`. |
| Ollama says “Model missing” | Run the `ollama pull` command above and check the exact `OLLAMA_MODEL` name against `ollama list`. |
| ComfyUI is offline | Start ComfyUI, verify its page opens, and check `COMFYUI_URL` in `.env`. |
| A model filename or node is missing | Check the three model paths above, update ComfyUI if needed, and test the included visual workflow in ComfyUI. Restart ComfyUI after installing models. |
| GPU memory error | Stop other GPU jobs and confirm the included workflow runs directly in ComfyUI. Smaller GPUs may need a different workflow, which this MVP does not automatically configure. |
| Port 8000 is already in use | Stop the other app instance, or run `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001` and open port 8001 instead. In PowerShell, use `.\.venv\Scripts\python.exe` for the executable. |
| A generation failed or was interrupted | Read the error shown in the app, fix the service problem, and use **Retry generation**. |

## Development and tests

After setup, run from the project folder:

```bash
.venv/bin/python -m pytest -q
```

On Windows, use `.\.venv\Scripts\python.exe -m pytest -q`. Tests use temporary
databases and mocked services; they do not consume GPU time or touch saved user
ratings. The suite covers ratings, feedback, sessions, statistics, aspect ratios,
database upgrades, and service coordination. Live generation has also been tested
with the Ubuntu configuration described above.

Deferred: history gallery, vision-based image analysis, controlled comparisons,
advanced model controls, public hosting, and automatic service startup.
