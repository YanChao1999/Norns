const { app, BrowserWindow } = require("electron");

const url = process.env.NORNS_URL || "http://127.0.0.1:8765";

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#1e1e1e",
    autoHideMenuBar: true,
    title: "Norns",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.loadURL(url);
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  app.quit();
});
