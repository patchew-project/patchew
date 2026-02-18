/**
 * Keyboard navigation helper - shared functionality
 *
 * Usage:
 *   KeyboardNav.init({
 *       items: $("selector"),           // jQuery collection of navigable items
 *       onActivate: function(item) {},  // Called when Enter/o is pressed
 *       activateLabel: "Open item",     // Label for the help dialog
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
    var pendingPrefix = null;
    var prefixTimeout = null;
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

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function showHelp(activateLabel, extraKeys) {
        var modal = $("#keyboard-help-modal");
        if (modal.length === 0) {
            var extraRows = "";
            if (extraKeys) {
                for (var i = 0; i < extraKeys.length; i++) {
                    extraRows += '<tr><td><kbd>' + escapeHtml(extraKeys[i].key) + '</kbd></td><td>' + escapeHtml(extraKeys[i].label) + '</td></tr>';
                }
            }
            modal = $('<div id="keyboard-help-modal" class="keyboard-help-overlay">' +
                '<div class="keyboard-help-dialog">' +
                '<h3>Keyboard Shortcuts</h3>' +
                '<table>' +
                '<tr><td><kbd>j</kbd></td><td>Move to next item</td></tr>' +
                '<tr><td><kbd>k</kbd></td><td>Move to previous item</td></tr>' +
                '<tr><td><kbd>o</kbd> / <kbd>Enter</kbd></td><td>' + escapeHtml(activateLabel) + '</td></tr>' +
                extraRows +
                '<tr><td><kbd>/</kbd></td><td>Focus search box</td></tr>' +
                '<tr><td><kbd>g</kbd> <kbd>h</kbd></td><td>Go to home page</td></tr>' +
                '<tr><td><kbd>g</kbd> <kbd>p</kbd></td><td>Go to project</td></tr>' +
                '<tr><td><kbd>g</kbd> <kbd>c</kbd></td><td>Go to cover letter</td></tr>' +
                '<tr><td><kbd>?</kbd></td><td>Show this help</td></tr>' +
                '<tr><td><kbd>Esc</kbd></td><td>Close this help</td></tr>' +
                '</table>' +
                '<button class="btn btn-secondary" onclick="$(\'#keyboard-help-modal\').removeClass(\'visible\')">Close</button>' +
                '</div></div>');
            $("body").append(modal);
        }
        modal.addClass("visible");
    }

    function hideHelp() {
        $("#keyboard-help-modal").removeClass("visible");
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
        var activateLabel = options.activateLabel || "Open selected item";
        var extraKeys = options.extraKeys || [];
        selectedIndex = -1;
        savedIndex = -1;

        // Clear selection when any element gets focus (e.g., browser find-in-page)
        boundFocusIn = function(e) {
            if (selectedIndex >= 0) {
                // Save selection when focusing our search input, discard otherwise
                if ($(e.target).is("#q")) {
                    clearSelection();
                } else if (!$(e.target).closest(".keyboard-help-dialog").length) {
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
            // Handle Escape to close help dialog
            if (e.key === "Escape") {
                if ($("#keyboard-help-modal").hasClass("visible")) {
                    hideHelp();
                    e.preventDefault();
                    return;
                }
            }

            // Ignore if help dialog is open
            if ($("#keyboard-help-modal").hasClass("visible")) {
                if (e.key === "?" || e.key === "Escape") {
                    hideHelp();
                    e.preventDefault();
                }
                return;
            }

            // Handle "g" prefix sequences
            if (pendingPrefix === "g") {
                clearTimeout(prefixTimeout);
                pendingPrefix = null;
                var path = window.location.pathname;
                var parts = path.split("/").filter(function(p) { return p; });
                switch (e.key) {
                    case "h":
                        window.location.href = "/";
                        e.preventDefault();
                        return;
                    case "p":
                        // Go to project
                        var project = null;
                        if (path === "/search") {
                            // Extract project from search query
                            var params = new URLSearchParams(window.location.search);
                            var q = params.get("q") || "";
                            var match = q.match(/project:(\S+)/);
                            if (match) {
                                project = match[1];
                            }
                        } else {
                            if (parts.length >= 1) {
                                project = parts[0];
                            }
                        }
                        if (project) {
                            window.location.href = "/" + project + "/";
                        }
                        e.preventDefault();
                        return;
                    case "c":
                        // Go to cover letter (when viewing a patch)
                        // URL structure: /project/thread_id/message_id/ (3 parts = patch view)
                        if (parts.length >= 3) {
                            window.location.href = "/" + parts[0] + "/" + parts[1] + "/";
                        }
                        e.preventDefault();
                        return;
                }
                return;
            }

            switch (e.key) {
                case "g":
                    pendingPrefix = "g";
                    prefixTimeout = setTimeout(function() {
                        pendingPrefix = null;
                    }, 1000);
                    e.preventDefault();
                    break;
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
                case "/":
                    var searchBox = $("#q");
                    if (searchBox.length) {
                        searchBox.focus().select();
                        e.preventDefault();
                    }
                    break;
                case "?":
                    showHelp(activateLabel, extraKeys);
                    e.preventDefault();
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
