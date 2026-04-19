import { loadPlugins } from './pluginGrid.js';
import { openPluginModal } from './pluginModal.js';

document.getElementById('searchInput').addEventListener('input', () => loadPlugins());
document.getElementById('sortSelect').addEventListener('change', () => loadPlugins());
document.getElementById('newPluginBtn').onclick = () => openPluginModal(null);

loadPlugins();