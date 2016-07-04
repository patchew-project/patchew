function patchew_api_do(method, data)
{
    data = {params: JSON.stringify(data)};
    console.log(data);
    return $.post("/api/" + method + "/", data);
}
