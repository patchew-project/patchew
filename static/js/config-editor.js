function confirm_leaving_page(enable) {
    if (enable) {
        window.onbeforeunload = function() {
            return "You have modified the configuration but have not saved it yet.";
        };
    } else {
        window.onbeforeunload = null;
    }
}

function save_done(btn, succeeded, error) {
    $(btn).text("Save");
    $(btn).removeClass("disabled");
    info = $("<div class=\"alert save-message\"></div>");
    if (succeeded) {
        info.addClass("alert-success");
        info.html("Saved");
        confirm_leaving_page(false);
    } else {
        info.addClass("alert-danger");
        info.html("Error: " + error);
    }
    info.insertBefore($(btn));
}

function collect_properties(btn, check_required) {
    properties = {};
    $(btn).parent().parent().find(".project-property").each(function () {
        path = $(this).data('property-path').split('.').reverse();
        parent = properties;
        while (path.length > 1) {
            key = path.pop();
            if (!(key in parent))
                parent[key] = {};
            parent = parent[key];
        }
        key = path[0];

        if (check_required && this.required && !this.value) {
            alert($(this).parent().find("label").html() + " is required!");
            $(this).focus();
            properties = false;
            return false;
        }
        if (this.type == "number") {
            val = parseInt(this.value);
            if (isNaN(val)) {
                alert("Invalid number for " + this.name);
                $(this).focus();
                properties = false;
                return false;
            }
        } else if (this.type == "checkbox") {
            if (this.checked) {
                val = true;
            } else {
                val = false;
            }
        } else {
            val = this.value;
        }
        parent[key] = val;
    });
    return properties;
}

function properties_save(btn) {
    if ($(btn).hasClass("disabled")) {
        return;
    }
    props = collect_properties(btn, true);
    if (!props) {
        return;
    }
    $(btn).addClass("disabled");
    $(btn).text("Saving...");
    $(btn).parent().find(".save-message").remove();
    options = {
        data: JSON.stringify(props),
        type: 'PUT',
        dataType: 'json',
        headers: { 'Content-Type': 'application/json' }
    };
    if ($(btn).data('csrf-token') != '') {
        options['headers']['X-CSRFToken'] = $(btn).data('csrf-token');
    }
    console.log(props);
    $.ajax($(btn).data('href'), options)
        .done(function (data) {
            save_done(btn, true);
        })
        .fail(function (data, text, error) {
            save_done(btn, false, error);
        });
}

function collect_items(container) {
    return container.find("> .items > .item > .item-heading > .item-name").map(function() {
        return $(this).text();
    }).get();
}

function map_add_item(btn) {
    name = window.prompt("Please input a name");
    if (!name || name == 'null') {
        return;
    }
    container = $(btn).parent().parent();
    if (collect_items(container).includes(name)) {
        alert(name + " already exists.");
        return;
    }
    if (name.indexOf(".") >= 0) {
        alert("Invalid name, no dot is allowed.");
        return;
    }
    tmpl = container.find(".item-template").html();
    nt = $(tmpl);
    nt.find(".item-name").text(name);
    prefix = nt.data('property-prefix') + '.' + name;
    nt.data('property-prefix', prefix);
    nt.find(".project-property").each(function() {
        old = $(this).data('property-path');
        $(this).data('property-path', prefix + old);
    });
    nt.find(".panel-collapse").collapse("show");
    container.find("> .items").append(nt);
    confirm_leaving_page(true);
}

function map_delete_item(btn) {
    item = $(btn).parent().parent().parent();
    name = item.find(".item-name").text();
    if (!window.confirm("Really delete '" + name +"'?")) {
        return;
    }
    item.remove();
    confirm_leaving_page(true);
}
function enum_change(which) {
    val = $(which).val();
    desc = $(which).parent().find("#enum-desc-" + val).html();
    $(which).parent().find("#enum-desc").html(desc);
}
