const $ = (id) => document.getElementById(id);
const tabs = [...document.querySelectorAll(".views button")];
const DELAY_NOTE = "This picture runs 2.5 seconds behind, so the erase covers the moment before their tag was read.";

function show(name) {
  tabs.forEach((tab) => tab.classList.toggle("on", tab.dataset.view === name));
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("on", view.id === name));
  if (name === "proof") loadProof();
  window.scrollTo({ top: 0 });
}

tabs.forEach((tab) => tab.addEventListener("click", () => show(tab.dataset.view)));

function describe(state) {
  if (!state || (!state.live && !state.stalled)) {
    return {
      headline: "The live camera is not shown on this page",
      detail: "Live video stays on the screen next to the camera, so nobody near it ends up on the internet. Proof and How it works are open here any time.",
      note: "no live video here",
    };
  }
  if (state.stalled || state.tripped) {
    return {
      headline: "The camera stopped, so the picture went black",
      detail: "When the software stops, it shows nothing. It never falls back to the raw video.",
      note: "black on purpose",
    };
  }
  const note = "live, 2.5 seconds behind";
  if (state.room) {
    return {
      headline: "This room asked not to be filmed",
      detail: "A room tag is switched on nearby, so everyone in view is hidden. Nobody had to wear anything.",
      note,
    };
  }
  if (state.holding) {
    return {
      headline: "A badge is nearby, but the camera cannot see its light",
      detail: "Until it finds the light, it hides everyone in view.",
      note,
    };
  }
  if (state.erased > 0) {
    const who = state.erased === 1 ? "1 person" : `${state.erased} people`;
    return { headline: `${who} asked to be left out`, detail: `They were erased inside the camera. ${DELAY_NOTE}`, note };
  }
  if (state.asking > 0) {
    return { headline: "A badge is nearby, and its wearer is out of view", detail: "Nobody in the picture is wearing it, so nobody is erased.", note };
  }
  return {
    headline: "Nobody nearby has asked to be left out",
    detail: "Put on a badge and switch it on. A few seconds later you are a black shape here.",
    note,
  };
}

function paint(state) {
  const words = describe(state);
  $("headline").textContent = words.headline;
  $("detail").textContent = words.detail;
  $("feedNote").textContent = words.note;
  $("factAsking").textContent = state && state.live ? state.asking ?? 0 : 0;
  $("factErased").textContent = state && state.live ? state.erased ?? 0 : 0;
  $("factRate").textContent = state && state.live ? Math.round(state.rate ?? 0) : 0;
}

let pulling = false;
let lastPicture = null;
let streaming = true;

async function pullFrame() {
  if (streaming || pulling || document.hidden || !$("camera").classList.contains("on")) return;
  pulling = true;
  try {
    const answer = await fetch(`operator.jpg?${Date.now()}`, { cache: "no-store" });
    if (answer.ok) {
      const picture = URL.createObjectURL(await answer.blob());
      $("frame").src = picture;
      if (lastPicture) URL.revokeObjectURL(lastPicture);
      lastPicture = picture;
    }
  } catch (error) {
    paint(null);
  }
  pulling = false;
}

$("frame").addEventListener("error", () => { streaming = false; });
$("frame").src = "operator.mjpg";

async function pullState() {
  if (document.hidden) return;
  try {
    const answer = await fetch(`state.json?${Date.now()}`, { cache: "no-store" });
    paint(answer.ok ? await answer.json() : null);
  } catch (error) {
    paint(null);
  }
}

setInterval(pullFrame, 70);
setInterval(pullState, 500);
pullState();

let proofLoaded = false;

function proofRow(number, what, conditions) {
  const row = document.createElement("div");
  row.className = "row";
  for (const [kind, words] of [["number", number], ["what", what], ["conditions", conditions]]) {
    const line = document.createElement("div");
    line.className = kind;
    line.textContent = words;
    row.appendChild(line);
  }
  return row;
}

async function loadProof() {
  if (proofLoaded) return;
  const rows = $("proofRows");
  rows.replaceChildren();
  try {
    const answer = await fetch(`proof.json?${Date.now()}`, { cache: "no-store" });
    if (!answer.ok) throw new Error("none");
    const proof = await answer.json();
    for (const item of proof.measured) rows.appendChild(proofRow(item.number, item.what, item.conditions));
    proofLoaded = true;
  } catch (error) {
    rows.appendChild(proofRow("Not measured yet", "The test results have not been loaded", "We only show numbers we measured ourselves."));
  }
}

const TOUR = [
  ["feed", "camera", "This is the only video that leaves the camera. Anyone wearing a badge is already blacked out by the time it gets here."],
  ["status", "camera", "This line says what the camera is doing and why, including when it hides everyone or shows nothing."],
  ["facts", "camera", "These counts come from the camera: badges it can hear, people it erased, and how fast it is running."],
  ["proofRows", "proof", "Proof lists what we measured in our own test, with the conditions under each number."],
  ["simSees", "how", "Flip these switches to see what the camera does in each case."],
];
let tourAt = -1;

function tourStep(index) {
  document.querySelectorAll(".spot").forEach((node) => node.classList.remove("spot"));
  tourAt = index;
  if (index < 0 || index >= TOUR.length) {
    $("tour").hidden = true;
    tourAt = -1;
    show("camera");
    return;
  }
  const [target, view, words] = TOUR[index];
  show(view);
  $("tourText").textContent = words;
  $("tourNextWord").textContent = index === TOUR.length - 1 ? "Done" : "Next";
  $("tour").hidden = false;
  const node = $(target);
  node.classList.add("spot");
  node.scrollIntoView({ block: "center", behavior: "smooth" });
}

$("tourStart").addEventListener("click", () => tourStep(0));
$("tourNext").addEventListener("click", () => tourStep(tourAt + 1));
$("tourEnd").addEventListener("click", () => tourStep(-1));

const welcome = $("welcome");
$("welcomeTour").addEventListener("click", () => { welcome.close(); tourStep(0); });
$("welcomeSkip").addEventListener("click", () => welcome.close());
try {
  if (!localStorage.getItem("blackout-welcomed")) {
    localStorage.setItem("blackout-welcomed", "1");
    welcome.showModal();
  }
} catch (error) {
  welcome.showModal();
}

const sim = { matched: false, seenFor: 0, last: performance.now() };
const SIM_PICTURES = ["sim_front", "sim_back", "sim_one", "sim_one_back", "sim_all", "sim_all_back"];
SIM_PICTURES.forEach((name) => { new Image().src = `img/${name}.jpg`; });

function simPicture(node, name) {
  const wanted = name ? `img/${name}.jpg` : "";
  if (node.dataset.shown === wanted) return;
  node.dataset.shown = wanted;
  if (name) node.src = wanted;
  node.style.visibility = name ? "visible" : "hidden";
}

function drawSim(now) {
  const step = Math.min(0.5, (now - sim.last) / 1000);
  sim.last = now;
  const tagOn = $("simTag").checked;
  const covered = $("simBack").checked;
  const running = $("simRun").checked;
  if (!tagOn) { sim.matched = false; sim.seenFor = 0; }
  if (tagOn && !covered) { sim.seenFor += step; if (sim.seenFor >= 2) sim.matched = true; }
  if (tagOn && covered && !sim.matched) sim.seenFor = 0;
  const holding = tagOn && !sim.matched;
  const turned = covered ? "_back" : "";

  simPicture($("simSees"), covered ? "sim_back" : "sim_front");
  let leaves = covered ? "sim_back" : "sim_front";
  if (!running) leaves = "";
  else if (holding) leaves = `sim_all${turned}`;
  else if (tagOn) leaves = `sim_one${turned}`;
  simPicture($("simLeaves"), leaves);

  let why = "Badge off. Nobody is asking, so nobody is erased.";
  if (!running) why = "The software stopped, so the camera shows nothing. It never falls back to the raw video.";
  else if (holding && covered) why = "The camera hears a badge over Bluetooth but cannot see its light, so it hides everyone in view.";
  else if (holding) why = "The camera hears the badge and is looking for its light. Until it finds it, everyone in view stays hidden.";
  else if (tagOn && covered) why = "The badge is out of sight now, but the camera already matched it to this person and keeps them erased while it follows them.";
  else if (tagOn) why = "The camera found the badge's light on the person on the left. Only they are erased.";
  $("simWhy").textContent = why;
}

setInterval(() => drawSim(performance.now()), 250);
drawSim(performance.now());
