import { Device } from "https://cdn.skypack.dev/@twilio/voice-sdk";

let device = null;
let call = null;
let timerInterval = null;
let seconds = 0;

const callBtn = document.getElementById("callBtn");
const stopBtn = document.getElementById("stopBtn");
const timerEl = document.getElementById("timer");
const controls = document.getElementById("callControls");
const hero = document.querySelector(".hero");

function formatTime(sec) {
  const m = String(Math.floor(sec / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function startTimer() {
  seconds = 0;
  timerEl.textContent = "00:00";
  timerInterval = setInterval(() => {
    seconds++;
    timerEl.textContent = formatTime(seconds);
  }, 1000);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
  timerEl.textContent = "00:00";
}


async function getToken() {
  const res = await fetch("/token");
  return (await res.json()).token;
}

async function startCall() {
  if (call) return;

  hero.classList.add("in-call");
  callBtn.classList.add("hidden");
  controls.classList.remove("hidden");
  startTimer();

  try {
    if (!device) {
      const token = await getToken();

      device = new Device(token, {
        logLevel: "debug",
        codecPreferences: ["opus", "pcmu"]
      });

      device.on("error", stopCall);
      await device.register();
    }

    call = await device.connect();
    call.on("disconnect", stopCall);

  } catch {
    stopCall();
  }
}


function stopCall() {
  if (call) {
    call.disconnect();
    call = null;
  }

  if (device) {
    device.destroy();
    device = null;
  }

  stopTimer();
  hero.classList.remove("in-call");
  controls.classList.add("hidden");
  callBtn.classList.remove("hidden");
}


callBtn.addEventListener("click", startCall);
stopBtn.addEventListener("click", stopCall);
window.addEventListener("beforeunload", stopCall);
