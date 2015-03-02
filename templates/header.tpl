<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Patchew - {{title}}</title>

<!-- HTML5 shim and Respond.js for IE8 support of HTML5 elements and media queries -->
<!-- WARNING: Respond.js doesn't work if you view the page via file:// -->
<!--[if lt IE 9]>
      <script src="https://oss.maxcdn.com/html5shiv/3.7.2/html5shiv.min.js"></script>
      <script src="https://oss.maxcdn.com/respond/1.4.2/respond.min.js"></script>
    <![endif]-->
<link rel="stylesheet" href="/static/bootstrap.min.css">
<!-- jQuery (necessary for Bootstrap's JavaScript plugins) -->
<script src="/static/jquery.min.js"></script>
<style type="text/css">
.header {
    overflow: hidden;
    margin-top: 10px;
    margin-bottom: 10px;
    border-bottom-color: #a8c335;
    border-bottom-style: solid;
    border-bottom-width: 8px;
}
.title a {
    font-size: 28px;
    color: #777;
    font-weight: bold;
}
.title a:hover {
    text-decoration: none;
}
.smiley {
    color: #008900;
}
.search {
    margin-top: 5px;
}
.search input {
    box-shadow: none;
    -webkit-box-shadow: none;
    border-right: none;
}
.btn-search-help:hover {
    background-color: white;
    border-left: none;
    border-right: none;
}
.btn-search-help {
    border-left: none;
    border-right: none;
    padding-left: 5px;
    padding-right: 5px;
}
.search-go {
    padding-left: 30px;
    padding-right: 30px;
}
.search-help-text {
    display: none;
}
</style>
<script type="text/javascript">
$(function() {
    $(".btn-search-help").click(function () {
            $(".search-help-text").toggle();
    });
});
</script>
</head>
<body>
<div class="col-lg-12 container">
    <div class="header">
        <div class="title col-lg-2">
            <a href="/"><span class="smiley">:p</span>atchew</a></h1>
        </div>
        <div class="col-lg-4"></div>
        <div class="search col-lg-6">
            <form role="search" method="GET" action="/">
                <div class="form-group">
                    <div class="input-group">
                        <input type="search" class="form-control" name="search" placeholder="Search" value="{{locals().get('search') or ""}}">
                        <span class="input-group-btn">
                            <button type="button" class="btn btn-default btn-search-help"><span class="badge">?</span></button>
                            <input type="submit" class="btn btn-success search-go" value="Go"/>
                        </span>
                    </div>
                </div>
            </form>
        </div>
    </div>
    <pre class="search-help-text">{{locals().get('search_help', '')}}</pre>
