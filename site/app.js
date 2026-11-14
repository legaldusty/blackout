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
      headline: "The camera is off right now",
      detail: "When it is on, this page shows the only picture that leaves it. The simulation in How it works runs any time.",
      note: "camera off",
    };
  }
  if (state.stalled || state.tripped) {
    return {
      headline: "The camera stopped, so the picture went black",
      detail: "Blackout fails closed. No frame is better than a raw frame.",
      note: "black on purpose",
    };
  }
  const note = "live, 2.5 seconds behind";
  if (state.holding) {
    return {
      headline: "A tag is nearby that the camera cannot see yet",
      detail: "Until it finds the light, everyone it has not matched stays hidden.",
      note,
    };
  }
  if (state.erased > 0) {
    const who = state.erased === 1 ? "1 person" : `${state.erased} people`;
    return { headline: `${who} asked to be left out`, detail: `They were erased inside the camera. ${DELAY_NOTE}`, note };
  }
  if (state.asking > 0) {
    return { headline: "A tag is nearby, and its wearer is out of view", detail: "Nobody in the picture is wearing it, so nobody is erased.", note };
  }
  return {
    headline: "Nobody nearby has asked to be left out",
    detail: "Clip on a tag and switch it on. You turn into a silhouette here within a few seconds.",
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

async function pullFrame() {
  if (pulling || document.hidden || !$("camera").classList.contains("on")) return;
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

async function pullState() {
  if (document.hidden) return;
  try {
    const answer = await fetch(`state.json?${Date.now()}`, { cache: "no-store" });
    paint(answer.ok ? await answer.json() : null);
  } catch (error) {
    paint(null);
  }
}

setInterval(pullFrame, 90);
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
    rows.appendChild(proofRow("Not measured yet", "We run the recorded tests once the hardware is built", "This page stays empty on purpose until then. We do not show numbers we have not measured."));
  }
}

const TOUR = [
  ["feed", "camera", "This is the only picture that leaves the camera. Anyone wearing a tag is already a silhouette by the time it gets here."],
  ["status", "camera", "This line says what the camera did and why. It also tells you when the camera is hiding everyone, or has gone black on purpose."],
  ["facts", "camera", "Live counts straight from the camera: tags it can hear, people it erased, and how fast it is running."],
  ["proofRows", "proof", "Proof holds the numbers we measured ourselves, with the test conditions under each one."],
  ["simSees", "how", "How it works has a simulation. Flip the switches to see each safety rule kick in."],
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
  $("tourNext").firstChild.textContent = index === TOUR.length - 1 ? "Done " : "Next ";
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

const PATTERN = [0, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1];
const sim = { matched: false, seenFor: 0, last: performance.now() };

function figure(pen, x, ground, scale, color) {
  pen.fillStyle = color;
  pen.beginPath();
  pen.ellipse(x, ground - 290 * scale, 31 * scale, 35 * scale, 0, 0, Math.PI * 2);
  pen.fill();
  pen.beginPath();
  pen.roundRect(x - 60 * scale, ground - 250 * scale, 120 * scale, 170 * scale, 44 * scale);
  pen.fill();
  pen.beginPath();
  pen.roundRect(x - 42 * scale, ground - 130 * scale, 84 * scale, 130 * scale, 18 * scale);
  pen.fill();
}

function backdrop(pen, width, height) {
  pen.fillStyle = "#292929";
  pen.fillRect(0, 0, width, height);
  pen.fillStyle = "#383838";
  pen.fillRect(0, height * 0.72, width, height * 0.28);
}

function drawSim(now) {
  const seconds = now / 1000;
  const step = Math.min(0.1, (now - sim.last) / 1000);
  sim.last = now;
  const tagOn = $("simTag").checked;
  const covered = $("simBack").checked;
  const running = $("simRun").checked;
  if (!tagOn) { sim.matched = false; sim.seenFor = 0; }
  if (tagOn && !covered) { sim.seenFor += step; if (sim.seenFor >= 2) sim.matched = true; }
  if (tagOn && covered && !sim.matched) sim.seenFor = 0;
  const holding = tagOn && covered && !sim.matched;

  const sees = $("simSees").getContext("2d");
  const leaves = $("simLeaves").getContext("2d");
  const width = 640;
  const height = 360;
  const ground = height * 0.8;
  const people = [
    { x: 130 + Math.sin(seconds * 0.5) * 18, scale: 0.72, tagged: false },
    { x: 320 + Math.sin(seconds * 0.35 + 1) * 26, scale: 0.8, tagged: true },
    { x: 510 + Math.sin(seconds * 0.6 + 2) * 14, scale: 0.64, tagged: false },
  ];

  backdrop(sees, width, height);
  for (const person of people) {
    figure(sees, person.x, ground, person.scale, "#8c8c8c");
    if (!person.tagged || !tagOn) continue;
    const chest = ground - 200 * person.scale;
    sees.strokeStyle = "#ffffff";
    sees.lineWidth = 1.5;
    for (const radius of [22, 34]) {
      sees.globalAlpha = 0.25 + 0.2 * Math.sin(seconds * 4 - radius / 10);
      sees.beginPath();
      sees.arc(person.x, chest, radius, 0, Math.PI * 2);
      sees.stroke();
    }
    sees.globalAlpha = 1;
    if (!covered && PATTERN[Math.floor(seconds * 15) % PATTERN.length]) {
      sees.fillStyle = "#e5231b";
      sees.beginPath();
      sees.arc(person.x, chest, 7, 0, Math.PI * 2);
      sees.fill();
    }
  }

  if (!running) {
    leaves.fillStyle = "#000000";
    leaves.fillRect(0, 0, width, height);
  } else {
    backdrop(leaves, width, height);
    for (const person of people) {
      const erased = holding || (tagOn && person.tagged);
      figure(leaves, person.x, ground, erased ? person.scale * 1.06 : person.scale, erased ? "#050505" : "#8c8c8c");
    }
  }

  let why = "Tag off. Nobody is asking, so nothing is erased. Try covering the tag before you switch it on.";
  if (!running) why = "The software stopped, so the output is black. It never falls back to the raw picture.";
  else if (holding) why = "The camera hears a tag over radio but cannot find its light. It hides everyone it has not matched.";
  else if (tagOn && covered) why = "The tag is covered now, but the camera already matched it to this person and keeps them erased while it tracks them.";
  else if (tagOn) why = "Radio says a tag is here. The blinking light, drawn in red so you can see it, shows which person. Only they are erased.";
  $("simWhy").textContent = why;
  requestAnimationFrame(drawSim);
}

requestAnimationFrame(drawSim);
