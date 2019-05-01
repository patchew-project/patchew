function current_project() {
    return $('h2').text();
}

function save_done(btn, succeeded, error) {
    $(btn).text("Save");
    $(btn).removeClass("disabled");
    info = $("<div class=\"alert save-message\"></div>");
    if (succeeded) {
        info.addClass("alert-success");
        info.html("Saved");
    } else {
        info.addClass("alert-danger");
        info.html("Error: " + error);
    }
    info.insertBefore($(btn));
}

function collect_properties(btn, check_required) {
    properties = {};
    $(btn).parent().parent().find(".project-property").each(function () {
        path = $(this).data('property-path');
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
        properties[path] = val;
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
    patchew_api_do("set-project-properties",
                   { project: current_project(),
                     properties: props })
        .done(function (data) {
            save_done(btn, true);
        })
        .fail(function (data, text, error) {
            save_done(btn, false, error);
        });
}

function collect_items(btn) {
    $(btn).parent().parent().find(".map-item");
    return {};
}

function map_add_item(btn) {
    name = window.prompt("Please input a name");
    if (!name || name == 'null') {
        return;
    }
    container = $(btn).parent().parent();
    if (name in collect_items(btn)) {
        alert(test_name + " already exists.");
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
}

function map_delete_item(btn) {
    item = $(btn).parent().parent().parent();
    name = item.find(".item-name").text();
    prefix = item.data('property-prefix') + ".";
    if (!window.confirm("Really delete '" + name +"'?")) {
        return;
    }
    $(btn).addClass("disabled");
    $(btn).text("Deleting...");
    $(btn).parent().find(".delete-message").remove();
    patchew_api_do("delete-project-properties-by-prefix",
                   { project: current_project(),
                     prefix: prefix })
        .done(function (data) {
            item.remove();
        })
        .fail(function (data, text, error) {
            $(btn).removeClass("disabled");
            $(btn).text("Delete");
            info = $("<div class=\"alert alert-danger delete-message\"></div>");
            info.html("Error: " + error);
            info.insertBefore($(btn));
        });
}
function enum_change(which) {
    val = $(which).val();
    desc = $(which).parent().find("#enum-desc-" + val).html();
    $(which).parent().find("#enum-desc").html(desc);
}
