const $ = (id) => document.getElementById(id);
let state = null;
let pending = false;
let renderKey = "";
let ratingFor = null;
let nameFor = null;
let ratioFor = null;
let ratiosLoaded = false;
let sessions = [];
let refreshVersion = 0;

const number = (value) => value == null ? "—" : Number(value).toFixed(1);

function sessionSummary() {
  const session = sessions.find((s) => s.id === $("sessions").value);
  $("session-summary").textContent = session
    ? `${new Date(session.created_at).toLocaleDateString()} · ${session.image_count} ${session.image_count === 1 ? "image" : "images"} · ${session.rated_count} ${session.rated_count === 1 ? "rating" : "ratings"} · average ${number(session.mean_score)}`
    : "Sessions are saved automatically on this computer.";
  $("load-session").disabled = !session || session.id === state?.session?.id || pending || state?.busy;
}

async function refreshSessions() {
  sessions = await api("/api/sessions");
  const selected = $("sessions").value;
  $("sessions").replaceChildren(new Option("Choose a session…", ""));
  for (const session of sessions) {
    $("sessions").add(new Option(session.name, session.id));
  }
  $("sessions").value = sessions.some((s) => s.id === selected) ? selected : state?.session?.id ?? "";
  sessionSummary();
}

function ratingDirty() {
  const g = state?.generation;
  return g?.status === "complete" && ($("score").value !== String(g.score ?? "") || $("feedback").value.trim() !== (g.feedback ?? ""));
}

function ratioDirty() {
  return $("aspect-ratio").value !== (state?.session?.aspect_ratio ?? "1:1");
}

function canSwitch() {
  const nameDirty = $("session-name").value.trim() !== (state?.session?.name ?? "");
  const ideasDirty = !state?.session && $("preferences").value.trim();
  return !(ratingDirty() || ratioDirty() || nameDirty || ideasDirty) || confirm("You have unsaved changes. Switch sessions without saving them?");
}

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
  if (!ratiosLoaded) {
    $("aspect-ratio").replaceChildren(...state.aspect_ratios.map((r) => new Option(r.label, r.aspect_ratio)));
    ratiosLoaded = true;
  }
  const ratioKey = JSON.stringify([session?.id, session?.aspect_ratio]);
  if (ratioFor !== ratioKey) {
    $("aspect-ratio").value = session?.aspect_ratio ?? "1:1";
    ratioFor = ratioKey;
  }
  $("aspect-ratio").disabled = locked;
  const nextFormat = state.aspect_ratios.find((r) => r.aspect_ratio === $("aspect-ratio").value);
  $("next-size").textContent = `${nextFormat.width} × ${nextFormat.height}`;
  const displayedFormat = g?.image_format ?? nextFormat;
  $("canvas").style.aspectRatio = `${displayedFormat.width} / ${displayedFormat.height}`;
  $("image-size").hidden = !g;
  $("image-size").textContent = g ? `${g.aspect_ratio} · ${displayedFormat.width} × ${displayedFormat.height}` : "";
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
  const ratingKey = JSON.stringify([g?.id, g?.score, g?.feedback, g?.rated_at]);
  if (ratingFor !== ratingKey) {
    $("score").value = g?.score ?? "";
    $("feedback").value = g?.feedback ?? "";
    ratingFor = ratingKey;
  }
  const nameKey = JSON.stringify([session?.id, session?.name]);
  if (nameFor !== nameKey) {
    $("session-name").value = session?.name ?? "";
    nameFor = nameKey;
  }
  $("session-name").disabled = locked;
  $("rename").hidden = !session;
  $("rename").disabled = locked;
  $("sessions").disabled = locked;
  sessionSummary();
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
  $("feedback").disabled = locked;
  $("save-rating").disabled = locked;
  $("rate").disabled = locked;
  $("rating-note").textContent = ratingDirty() || ratioDirty() ? "Unsaved changes — choose a save button below."
    : g?.score != null ? "Rating saved. You can update it or generate the next image." : "Your score helps shape the next image.";
  $("statistics").hidden = !session;
  const stats = state.statistics;
  $("stat-count").textContent = stats.count;
  $("stat-mean").textContent = number(stats.mean);
  $("stat-best").textContent = stats.best ?? "—";
  $("stat-deviation").textContent = number(stats.standard_deviation);
  $("statistics-note").textContent = "Standard deviation shows how widely your scores vary. " +
    (stats.count < 2 ? "Rate at least two images to see it." : stats.count < 5 ? "Still early: fewer than five ratings give limited evidence." : "Based on all saved ratings in this session.");
  $("retry").hidden = g?.status !== "error";
  $("retry").disabled = locked;
  $("placeholder").classList.toggle("working", busy);
}

async function refresh() {
  const version = ++refreshVersion;
  const updated = await api("/api/state");
  if (version !== refreshVersion) return;
  const completed = updated.generation?.status === "complete" &&
    (state?.generation?.id !== updated.generation.id || state?.generation?.status !== "complete");
  state = updated;
  render();
  if (completed) await refreshSessions();
}

async function action(callback) {
  if (pending) return;
  pending = true;
  ++refreshVersion;
  render();
  message("");
  try {
    await callback();
    await refresh();
    await refreshSessions();
  } catch (error) {
    message(error.message);
  } finally {
    pending = false;
    render();
  }
}

$("mutation").addEventListener("input", () => { $("mutation-value").textContent = `${$("mutation").value}%`; });
$("aspect-ratio").addEventListener("change", render);
$("generate-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(() => api("/api/generate", {name: $("session-name").value.trim(), preferences: $("preferences").value.trim(), mutation: Number($("mutation").value), aspect_ratio: $("aspect-ratio").value}));
});
$("rating-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const score = Number($("score").value);
  if (!$("score").value || !Number.isInteger(score) || score < 0 || score > 100) return;
  const generateNext = event.submitter?.id === "rate";
  action(() => api(`/api/generations/${state.generation.id}/rate`, {
    score, feedback: $("feedback").value.trim(), mutation: Number($("mutation").value), generate_next: generateNext,
    aspect_ratio: $("aspect-ratio").value,
  }));
});
$("score").addEventListener("input", render);
$("feedback").addEventListener("input", render);
$("sessions").addEventListener("change", sessionSummary);
$("name-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (state?.session) action(() => api(`/api/sessions/${state.session.id}/rename`, {name: $("session-name").value.trim()}));
});
$("load-session").addEventListener("click", () => {
  if (canSwitch()) action(() => api(`/api/sessions/${$("sessions").value}/load`, {}));
});
$("retry").addEventListener("click", () => action(() => api(`/api/generations/${state.generation.id}/retry`, {})));
$("reset").addEventListener("click", () => {
  if (!canSwitch()) return;
  action(async () => {
  await api("/api/reset", {});
  $("preferences").value = "";
  $("mutation").value = 20;
  $("sessions").value = "";
  });
});

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
  try { if (!pending) await refresh(); }
  catch { message("Cannot reach Image Personalizer. Make sure the app is running; this page will reconnect automatically."); renderKey = ""; }
  setTimeout(poll, 1500);
}
health();
setInterval(health, 15000);
poll();
refreshSessions().catch((error) => message(error.message));
window.addEventListener("beforeunload", (event) => {
  if (ratingDirty() || ratioDirty()) { event.preventDefault(); event.returnValue = ""; }
});
