# Image Personalizer

A barebones local app: enter a few preferences, generate an image, give it a score
from 0–100, and let those scores guide the next prompt.

## Run

Keep Ollama and your existing ComfyUI installation running. Then:

```bash
cd "/home/riz/Documents/ChatGPT/Image Personalizer"
./start.sh
```

Open **http://127.0.0.1:8000**. Stop the app with **Ctrl+C** in its terminal.
This does not stop Ollama or ComfyUI. If an image job is already running in
ComfyUI, it can finish there; restart the app and use Retry to recover it.

Dependencies are already installed in `.venv`. To recreate that environment:

```bash
./setup.sh
```

Python 3.12+ with `venv` is required. If Ubuntu reports a missing `ensurepip`,
install `python3-venv` using apt, then run setup again. No Node.js, cloud account,
or API key is required.

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
VAE; the selector
shows the resulting pixel dimensions. The current image's ratio and dimensions
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
Retry preserves an existing prompt and seed and
reconnects to an existing ComfyUI job where possible.

## Local services and configuration

Defaults:

- Ollama: `http://127.0.0.1:11434`
- Model: `qwen3-vl:8b-instruct-q4_K_M`
- ComfyUI: `http://127.0.0.1:8188`
- App: `http://127.0.0.1:8000`

Copy `.env.example` to `.env` to change the service addresses, model, or data
directory. Restart the app after changes. This MVP is for a single local user,
one server process, and one generation at a time. Use `start.sh` without adding
multiple workers. Avoid running separate Ollama chats or ComfyUI jobs during
generation; the app checks the ComfyUI queue before freeing models or submitting.

The application requests ComfyUI model unloading before writing a new prompt,
waits for its GPU allocations to clear, then calls Ollama. LLM responses have a
512-token cap, a 16,384-token context window, and a three-minute request timeout.
Ollama uses `keep_alive: 0`,
with an explicit unload check before image generation. ComfyUI models may remain
loaded while you rate an image and are freed before the next LLM turn. Image jobs
have a twenty-minute observation timeout; Retry reconnects to a still-running job.

## Workflow

`workflows/source_qwen_image_2_1.json` is the original visual workflow copied from
`/home/riz/ComfyUI/user/default/workflows/image_qwen_image_2_1_t2i.json`.
`workflows/qwen_image_2_1.json` is its flattened API graph, preserving:

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
with the app stopped. On the first startup after this update, the app creates a
SQLite backup in `data/backups/` before adding any missing session names, feedback,
or aspect-ratio fields.
Existing sessions get names from their starting preferences; their scores and
images are retained. Migration backups cover the database; back up `data/images/`
as well for a complete copy. Local data and backups are excluded from Git.

## Verification

```bash
.venv/bin/pytest -q
```

Tests use temporary databases and mocked services; they do not consume GPU time
or touch personal ratings. A separate live smoke test was also performed using
the installed Ollama model and ComfyUI workflow. Live test data is kept outside
the app's normal data directory.

Deferred: history gallery, vision-based image analysis,
controlled comparisons, advanced model controls, and automatic service startup.
