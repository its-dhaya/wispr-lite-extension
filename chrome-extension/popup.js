const toggle = document.getElementById("toggle");
const statusEl = document.getElementById("status");

function renderStatus(enabled) {
  statusEl.textContent = enabled ? "Running locally" : "Stopped";
  statusEl.className = "status " + (enabled ? "on" : "off");
}

chrome.storage.local.get("wisprEnabled").then(({ wisprEnabled }) => {
  toggle.checked = !!wisprEnabled;
  renderStatus(!!wisprEnabled);
});

toggle.addEventListener("change", () => {
  chrome.runtime.sendMessage({ type: "SET_ENABLED", enabled: toggle.checked });
  renderStatus(toggle.checked);
});
