const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('sublyaiDesktop', {
  isDesktopApp: true,
});