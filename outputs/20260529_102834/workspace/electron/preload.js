// electron/preload.js
// All of the Node.js APIs are available in the preload process.
// It has the same sandbox as a Chrome extension.
const { contextBridge, ipcRenderer } = require('electron');

// Expose some APIs to the renderer process
contextBridge.exposeInMainWorld('electron', {
  // Example: a function to send a message to the main process
  sendMessage: (channel, data) => {
    ipcRenderer.send(channel, data);
  },
  // Example: a function to receive a message from the main process
  onMessage: (channel, callback) => {
    ipcRenderer.on(channel, (event, ...args) => callback(...args));
  },
  // You can expose other Electron APIs here if needed, but be cautious about security.
});