/** Shell header PanelLeft toggles table list on /db via this event. */
export function dispatchDbExplorerToggleTables() {
  window.dispatchEvent(new CustomEvent('db-explorer-toggle-tables'))
}
