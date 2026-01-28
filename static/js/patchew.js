function patchew_toggler_onclick(which)
{
    tgt = $(which).parent().find(".card-collapse");
    tgt.collapse("toggle");
    return false;
}
function add_fixed_scroll_events()
{
    $(window).scroll(function() {
        var pre_fixed = $('#pre-fixed');
        var fixed = $('#fixed');
        // add/remove the col-lg-NN attribute to the #fixed element, because
        // "position: fixed" computes the element's width according to the document's
        fixed.toggleClass('fixed ' + fixed.parent().attr('class'),
                          $(window).scrollTop() + 10 >= pre_fixed.offset().top + pre_fixed.height());
    })
}

function copy_to_clipboard(input) {
    if (input.value == '') {
        return;
    }

    var origSelectionStart = input.selectionStart;
    var origSelectionEnd = input.selectionEnd;
    var origFocus = typeof document.activeElement.focus === "function" ? document.activeElement : null;

    // copy the selection.  Note that the old selection is not restored unless
    // an error happens, to give the user feedback that the copy has happened.
    input.focus();
    input.setSelectionRange(0, input.value.length);
    try {
       document.execCommand("copy");
    } catch(e) {
        input.setSelectionRange(origSelectionStart, origSelectionEnd);
        if (origFocus) {
            origFocus.focus();
        }
    }
}

function copy_text_to_clipboard(text, element) {
    var originalText = element ? element.textContent : null;

    function showCopied() {
        if (element && originalText) {
            element.textContent = "Copied!";
            setTimeout(function() {
                element.textContent = originalText;
            }, 1000);
        }
    }

    // Try modern clipboard API first
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function() {
            showCopied();
        }, function(err) {
            console.error("Clipboard API failed, trying fallback:", err);
            execCommandCopy(text, showCopied);
        });
    } else {
        execCommandCopy(text, showCopied);
    }
}

function execCommandCopy(text, onSuccess) {
    var textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.cssText = "position:fixed;top:0;left:0;width:1px;height:1px;padding:0;border:none;outline:none;box-shadow:none;background:transparent;";
    document.body.appendChild(textarea);

    var selection = document.getSelection();
    var range = document.createRange();
    range.selectNodeContents(textarea);
    selection.removeAllRanges();
    selection.addRange(range);
    textarea.setSelectionRange(0, text.length);

    try {
        var result = document.execCommand("copy");
        if (result && onSuccess) {
            onSuccess();
        }
    } catch(e) {
        console.error("execCommand copy failed:", e);
    }

    selection.removeAllRanges();
    document.body.removeChild(textarea);
}
