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

1. Enter starting ideas, such as `Japanese, floral`.
2. Set Mutation (20% by default) and click **Generate first image**.
3. Enter an integer score from 0–100, then **Save & generate next**.
4. Adjust Mutation between generations if desired.
5. **Start over** begins a fresh session and leaves previous data on disk.

Mutation is a probability, decided by the application for each image. At 0%,
the LLM refines promising directions. At 100%, it explores a new direction each
time. Both modes retain the starting ideas. A random image seed still introduces
variation at 0%. The first generation interprets the ideas without rating history.

The LLM receives up to ten distinct scored examples: four highest-rated, two
lowest-rated, and four most recent (overlaps are included once). This is prompting
with stored feedback, not model training. Ratings suggest preferences; they don't
prove that a particular phrase caused a better image or guarantee rising scores.

Refreshing or reopening the page restores the active session. Scoring and creating
the next generation are saved together. Repeated submissions of the same rating
return the same next generation. Retry preserves an existing prompt and seed and
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
512-token cap and a three-minute request timeout. Ollama uses `keep_alive: 0`,
with an explicit unload check before image generation. ComfyUI models may remain
loaded while you rate an image and are freed before the next LLM turn. Image jobs
have a twenty-minute observation timeout; Retry reconnects to a still-running job.

## Workflow

`workflows/source_qwen_image_2_1.json` is the original visual workflow copied from
`/home/riz/ComfyUI/user/default/workflows/image_qwen_image_2_1_t2i.json`.
`workflows/qwen_image_2_1.json` is its flattened API graph, preserving:

- Qwen Image 2.1 INT8 ConvRot, Qwen3-VL 8B INT8 ConvRot encoder, BF16 VAE
- ResolutionSelector: square, 1 megapixel, multiple of 8 → 1024×1024
- 25 steps, CFG 1, Euler sampler, simple scheduler, denoise 1, batch size 1
- Empty negative prompt; PNG 8-bit sRGB output

Each run changes the positive prompt and seed. Output names use
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

`data/personalizer.sqlite3` stores sessions, scores, prompts, seeds, mutation
decisions, exact submitted workflow graphs, and LLM request context.
`data/images/` stores independent copies of completed PNGs. Removing a ComfyUI
output does not remove the app's saved copy. Back up the entire `data/` folder
with the app stopped. Old sessions remain stored but there is no gallery or
session picker in this first version.

## Verification

```bash
.venv/bin/pytest -q
```

Tests use temporary databases and mocked services; they do not consume GPU time
or touch personal ratings. A separate live smoke test was also performed using
the installed Ollama model and ComfyUI workflow. Live test data is kept outside
the app's normal data directory.

Deferred: history gallery, written feedback, vision-based image analysis,
controlled comparisons, advanced model controls, and automatic service startup.
