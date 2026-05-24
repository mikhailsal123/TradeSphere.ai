/**
 * Shared saved-strategy list (Studio, Dashboard import pane, Live Trading).
 */
(function (global) {
    "use strict";

    const STORAGE_KEY = "tradesphere_strategies_v1";

    function loadSavedStrategies() {
        try {
            const raw = global.localStorage.getItem(STORAGE_KEY);
            const list = raw ? JSON.parse(raw) : [];
            return Array.isArray(list) ? list : [];
        } catch (_e) {
            return [];
        }
    }

    function persistStrategies(list) {
        try {
            global.localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
        } catch (e) {
            console.warn("Could not persist strategies:", e);
        }
    }

    function sortByUpdatedDesc(list) {
        return list.slice().sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
    }

    global.TradeSphereStrategies = {
        STORAGE_KEY,
        loadSavedStrategies,
        persistStrategies,
        sortByUpdatedDesc,
    };

})(typeof window !== "undefined" ? window : globalThis);
