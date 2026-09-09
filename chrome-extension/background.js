// Wispr Lite background service worker.
//
// The trick that makes "disable extension -> local program shuts down" work
// is native messaging's process lifecycle: chrome.runtime.connectNative()
// SPAWNS the native host process, and disconnecting the port (or the
// extension being disabled/unloaded) causes Chrome to CLOSE that process's
// stdin, which the host watches for and exits on. So all we do here is
// open/close a native messaging port based on the stored toggle state.
//
// Note: an open native messaging port is one of the few things that keeps
// an MV3 service worker alive indefinitely, so this connection persists
// even if the SW would otherwise go idle.

const HOST_NAME = "com.wispr_lite.host";
let port = null;

function connectHost() {
  if (port) return;
  port = chrome.runtime.connectNative(HOST_NAME);
  port.onDisconnect.addListener(() => {
    if (chrome.runtime.lastError) {
      console.error("Wispr Lite host disconnected:", chrome.runtime.lastError.message);
    }
    port = null;
  });
}

function disconnectHost() {
  if (port) {
    port.disconnect();
    port = null;
  }
}

async function syncState() {
  const { wisprEnabled } = await chrome.storage.local.get("wisprEnabled");
  if (wisprEnabled) {
    connectHost();
  } else {
    disconnectHost();
  }
}

chrome.runtime.onStartup.addListener(syncState);
chrome.runtime.onInstalled.addListener(syncState);

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "SET_ENABLED") {
    chrome.storage.local.set({ wisprEnabled: message.enabled });
    if (message.enabled) {
      connectHost();
    } else {
      disconnectHost();
    }
  }
});
