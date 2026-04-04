// ========== Card Filtering ==========
/**
 * Filters and reorders cards in a grid.
 * @param {Array} cardArray - Array of { element, item }.
 * @param {function} filterFn - Function(item) returns true if visible.
 * @param {function} sortFn - Optional function(a, b) for sorting items.
 * @param {HTMLElement} gridElement - The grid container.
 */
window.filterCards = function(cardArray, filterFn, sortFn, gridElement) {
    let visible = cardArray.filter(card => filterFn(card.item));
    if (sortFn) {
        visible.sort((a, b) => sortFn(a.item, b.item));
    }
    visible.forEach(card => gridElement.appendChild(card.element));
    cardArray.forEach(card => {
        card.element.style.display = visible.includes(card) ? 'flex' : 'none';
    });
};