/**
 * Keyboard navigation helper - shared functionality
 *
 * Usage:
 *   KeyboardNav.init({
 *       items: $("selector"),           // jQuery collection of navigable items
 *       onActivate: function(item) {},  // Called when Enter/o is pressed
 *       extraKeys: [                    // Optional extra key bindings
 *           { key: "n", label: "Next item", handler: function() {} }
 *       ]
 *   });
 */
var KeyboardNav = (function($) {
    var selectedIndex = -1;
    var savedIndex = -1;
    var items = $();
    var onActivate = null;
    var boundFocusIn = null;
    var boundKeyDown = null;

    function clearSelection() {
        items.removeClass("selected").attr("aria-selected", "false");
        savedIndex = selectedIndex;
        selectedIndex = -1;
    }

    function restoreSelection() {
        if (savedIndex >= 0 && savedIndex < items.length) {
            selectedIndex = savedIndex;
            items.eq(selectedIndex).addClass("selected");
        }
        savedIndex = -1;
    }

    function selectItem(index) {
        if (items.length === 0) return;
        if (index < 0) index = 0;
        if (index >= items.length) index = items.length - 1;
        items.removeClass("selected").attr("aria-selected", "false");
        selectedIndex = index;
        var item = items.eq(selectedIndex);
        if (item.length === 0) return;
        item.addClass("selected").attr("aria-selected", "true");
        item[0].scrollIntoView({block: "nearest"});
    }

    function activateSelected() {
        if (selectedIndex < 0 || !onActivate) return;
        onActivate(items.eq(selectedIndex), selectedIndex);
    }

    function init(options) {
        // Clean up previous handlers to prevent memory leaks on re-init
        if (boundFocusIn) {
            $(document).off("focusin", boundFocusIn);
        }
        if (boundKeyDown) {
            $(document).off("keydown", boundKeyDown);
        }

        items = options.items || $();
        onActivate = options.onActivate || null;
        var extraKeys = options.extraKeys || [];
        selectedIndex = -1;
        savedIndex = -1;

        // Clear selection when any element gets focus (e.g., browser find-in-page)
        boundFocusIn = function(e) {
            if (selectedIndex >= 0) {
                // Save selection when focusing our search input, discard otherwise
                if ($(e.target).is("#q")) {
                    clearSelection();
                } else {
                    items.removeClass("selected").attr("aria-selected", "false");
                    selectedIndex = -1;
                    savedIndex = -1;
                }
            }
        };
        $(document).on("focusin", boundFocusIn);

        boundKeyDown = function(e) {
            // Handle Escape in input fields to restore selection
            if ($(e.target).is("input, textarea, select")) {
                if (e.key === "Escape") {
                    $(e.target).blur();
                    restoreSelection();
                    e.preventDefault();
                }
                return;
            }

            switch (e.key) {
                case "j":
                    selectItem(selectedIndex + 1);
                    e.preventDefault();
                    break;
                case "k":
                    selectItem(selectedIndex - 1);
                    e.preventDefault();
                    break;
                case "o":
                case "Enter":
                    if (selectedIndex >= 0) {
                        activateSelected();
                        e.preventDefault();
                    }
                    break;
                default:
                    // Check extra keys
                    for (var i = 0; i < extraKeys.length; i++) {
                        if (e.key === extraKeys[i].key) {
                            extraKeys[i].handler();
                            e.preventDefault();
                            return;
                        }
                    }
            }
        };
        $(document).on("keydown", boundKeyDown);
    }

    return {
        init: init,
        select: selectItem,
        getSelectedIndex: function() { return selectedIndex; }
    };
})(jQuery);
