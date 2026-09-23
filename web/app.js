const $ = (id) => document.getElementById(id);
let state = null;
let pending = false;
let renderKey = "";
let ratingFor = null;

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Please check the values and try again.");
  return data;
}

function message(text) {
  $("error").textContent = text;
  $("error").hidden = !text;
}

function render() {
  if (!state) return;
  const {session, generation: g, busy, rated_count} = state;
  const locked = busy || pending;
  const key = JSON.stringify([session?.id, g?.id, g?.status, g?.error]);
  if (renderKey !== key) {
    if (session) $("preferences").value = session.preferences;
    if (!renderKey || session?.id !== $("preferences").dataset.session) {
      $("mutation").value = session?.mutation ?? 20;
      $("preferences").dataset.session = session?.id ?? "";
    }
    $("image-label").textContent = g ? `IMAGE ${String(g.sequence).padStart(2, "0")}` : "YOUR NEXT DISCOVERY";
    $("mode").hidden = !g;
    $("mode").textContent = g ? (g.mutated ? "Exploration" : "Refinement") : "";
    $("image").hidden = !g?.image_url;
    if (g?.image_url) $("image").src = g.image_url;
    else $("image").removeAttribute("src");
    $("placeholder").hidden = !!g?.image_url;
    $("prompt-details").hidden = !g?.prompt;
    $("prompt").textContent = g?.prompt ?? "";
    $("rationale").textContent = g?.rationale ?? "";
    const stages = {
      preparing: ["Making room for an idea.", "Preparing your next generation.", "Preparing…"],
      prompting: ["Finding a direction.", "Writing a prompt from your ideas and ratings.", "Writing your image prompt…"],
      generating: ["Your idea is taking shape.", "The first image can take longer while models load.", "Generating in ComfyUI…"],
      complete: ["", "", "Take a look, then give it a score."],
      error: ["Let’s try that again.", "Your session and any completed work are saved.", "Generation needs attention."],
    };
    const text = stages[g?.status] ?? ["An idea is all it takes.", "Your first image will appear here.", "Ready when you are."];
    $("stage-title").textContent = text[0];
    $("stage-description").textContent = text[1];
    $("status").textContent = text[2];
    message(g?.error ?? "");
    renderKey = key;
  }
  if (ratingFor !== g?.id) {
    $("score").value = "";
    ratingFor = g?.id;
  }
  $("mutation-value").textContent = `${$("mutation").value}%`;
  $("preferences").disabled = !!session || locked;
  $("mutation").disabled = locked;
  $("generate").hidden = !!g;
  $("generate").disabled = locked;
  $("reset").hidden = !session;
  $("reset").disabled = locked;
  $("saved-note").hidden = !session;
  $("session-count").textContent = session ? `${rated_count} ${rated_count === 1 ? "rating" : "ratings"} in this session` : "A fresh start";
  $("rating-form").hidden = g?.status !== "complete";
  $("score").disabled = locked;
  $("rate").disabled = locked;
  $("retry").hidden = g?.status !== "error";
  $("retry").disabled = locked;
  $("placeholder").classList.toggle("working", busy);
}

async function refresh() {
  state = await api("/api/state");
  render();
}

async function action(callback) {
  if (pending) return;
  pending = true;
  render();
  message("");
  try {
    await callback();
    await refresh();
  } catch (error) {
    message(error.message);
  } finally {
    pending = false;
    render();
  }
}

$("mutation").addEventListener("input", () => { $("mutation-value").textContent = `${$("mutation").value}%`; });
$("generate-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(() => api("/api/generate", {preferences: $("preferences").value.trim(), mutation: Number($("mutation").value)}));
});
$("rating-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const score = Number($("score").value);
  if (!$("score").value || !Number.isInteger(score) || score < 0 || score > 100) return;
  action(() => api(`/api/generations/${state.generation.id}/rate`, {score, mutation: Number($("mutation").value)}));
});
$("retry").addEventListener("click", () => action(() => api(`/api/generations/${state.generation.id}/retry`, {})));
$("reset").addEventListener("click", () => action(async () => {
  await api("/api/reset", {});
  $("preferences").value = "";
  $("mutation").value = 20;
}));

async function health() {
  try {
    const data = await api("/api/health");
    for (const name of ["ollama", "comfyui"]) {
      $(name).textContent = `${name === "ollama" ? "Ollama" : "ComfyUI"} · ${data[name].toLowerCase()}`;
      $(name).className = data[name] === "Ready" ? "ready" : "offline";
    }
  } catch { /* State polling below reports connection failures. */ }
}

async function poll() {
  try { await refresh(); }
  catch { message("Cannot reach Image Personalizer. Make sure the app is running; this page will reconnect automatically."); renderKey = ""; }
  setTimeout(poll, 1500);
}
health();
setInterval(health, 15000);
poll();
