/* SevenBox sync worker — holds WebSocket so messages arrive even when UI is janky */
let ws = null;
let url = "";
let latestState = null;
let latestTransport = null;
let latestFull = null;

function send(obj) {
  try {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
  } catch (e) {}
}

function connect(u) {
  url = u;
  try {
    if (ws) {
      try { ws.onclose = null; ws.close(); } catch (e) {}
    }
  } catch (e) {}
  try {
    ws = new WebSocket(url);
  } catch (e) {
    postMessage({ type: "ws_error", error: String(e) });
    return;
  }
  ws.onopen = function () {
    postMessage({ type: "ws_open" });
  };
  ws.onclose = function () {
    postMessage({ type: "ws_close" });
    // auto-reconnect
    setTimeout(function () {
      if (url) connect(url);
    }, 1000);
  };
  ws.onerror = function () {
    postMessage({ type: "ws_error", error: "error" });
  };
  ws.onmessage = function (ev) {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.type === "state") latestState = msg;
    if (msg.type === "transport") latestTransport = msg;
    if (msg.type === "full_sync") latestFull = msg;
    // Always notify main thread
    postMessage({ type: "msg", msg: msg });
  };
}

// Pump latest to main even if events were coalesced
setInterval(function () {
  postMessage({
    type: "pump",
    t: Date.now(),
    latestState: latestState,
    latestTransport: latestTransport,
    latestFull: latestFull,
    wsState: ws ? ws.readyState : -1
  });
}, 100);

onmessage = function (e) {
  const m = e.data || {};
  if (m.type === "connect") connect(m.url);
  if (m.type === "disconnect") {
    url = "";
    try { if (ws) ws.close(); } catch (e) {}
    ws = null;
  }
  if (m.type === "send") send(m.payload);
  if (m.type === "get_latest") {
    postMessage({
      type: "latest",
      latestState: latestState,
      latestTransport: latestTransport,
      latestFull: latestFull
    });
  }
};
