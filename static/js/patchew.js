function patchew_api_do(method, data)
{
    data = {params: JSON.stringify(data)};
    console.log(data);
    return $.post("/api/" + method + "/", data);
}
function patchew_toggler_onclick(which)
{
    tgt = $(which).parent().find(".panel-toggle");
    tgt.toggle();
    url = tgt.attr("data-content-url");
    if (tgt.find(".progress-bar") && url) {
        $.get(url, function (data) {
            tgt.html("<pre>" + data + "</pre>");
        });
    }
}
